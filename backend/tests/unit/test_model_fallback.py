import unittest
from unittest.mock import AsyncMock
from storyclaw.models.fallback import QuotaFallbackModel
from storyclaw.models.metering import Meter, active_meter

class Quota(Exception):
    status_code=429
    body={'error':{'code':'1113'}}

class Client:
    def __init__(self, error=None, chunks=()):
        self.error=error;self.chunks=chunks
        self.ainvoke=AsyncMock(side_effect=error) if error else AsyncMock(return_value='ok')
    def bind(self, **kwargs):return self
    def bind_tools(self, tools, **kwargs):return self
    async def astream(self, messages, **kwargs):
        for chunk in self.chunks:yield chunk
        if self.error:raise self.error

class FallbackTests(unittest.IsolatedAsyncioTestCase):
    def model(self, a, b):return QuotaFallbackModel([(lambda:a,'primary'),(lambda:b,'secondary')])
    async def test_quota_fallback_meter_uses_actual_model(self):
        reserve=AsyncMock(side_effect=['one','two']);settle=AsyncMock(return_value=0)
        token=active_meter.set(Meter(reserve,settle))
        try:self.assertEqual(await self.model(Client(Quota()),Client()).bind(max_tokens=10).bind_tools([]).ainvoke([]),'ok')
        finally:active_meter.reset(token)
        self.assertEqual([c.args[0] for c in reserve.call_args_list],['primary','secondary'])
        self.assertEqual(settle.await_count,2)
    async def test_no_fallback_on_timeout_or_auth_or_rate_limit(self):
        for error in [TimeoutError(),type('Auth',(Exception,),{'status_code':401})(),type('Rate',(Exception,),{'status_code':429})()]:
            second=Client()
            with self.assertRaises(type(error)):await self.model(Client(error),second).ainvoke([])
            second.ainvoke.assert_not_called()
    async def test_partial_stream_never_switches_models(self):
        second=Client(chunks=['wrong'])
        chunks=[]
        with self.assertRaises(Quota):
            async for c in self.model(Client(Quota(),['draft']),second).astream([]):chunks.append(c)
        self.assertEqual(chunks,['draft'])
    async def test_empty_stream_quota_switches_once(self):
        self.assertEqual([x async for x in self.model(Client(Quota()),Client(chunks=['new'])).astream([])],['new'])
    async def test_second_quota_propagates(self):
        with self.assertRaises(Quota):await self.model(Client(Quota()),Client(Quota())).ainvoke([])
    async def test_success_does_not_construct_backup(self):
        backup=AsyncMock()
        model=QuotaFallbackModel([(lambda:Client(),'primary'),(backup,'secondary')])
        self.assertEqual(await model.ainvoke([]),'ok');backup.assert_not_called()

    def test_test_catalog_preserves_encrypted_key_and_order(self):
        from app.services.platform.test_models import catalog_for_tests
        original={'models':[{'id':'glm-5.1','api_key_enc':'encrypted-placeholder','base_url':'https://open.bigmodel.cn/api/paas/v4','enabled':True}]}
        result=catalog_for_tests(original)
        self.assertEqual([m['id'] for m in result['models'][:2]], ['glm-4.5-air','glm-5.3-flash'])
        self.assertEqual(result['models'][0]['fallback_models'], ['glm-5.3-flash'])
        self.assertEqual(result['models'][1]['thinking'], 'enabled')
        self.assertEqual(result['models'][1]['api_key_enc'], 'encrypted-placeholder')
        self.assertTrue(original['models'][0]['enabled'])
        self.assertFalse(result['models'][2]['enabled'])

    def test_model_schema_keeps_fallback_configuration(self):
        from app.gateway.routers.admin import ModelCatalog
        catalog=ModelCatalog(models=[{'id':'one','display_name':'One','fallback_models':['two']}, {'id':'two','display_name':'Two'}])
        self.assertEqual(catalog.model_dump()['models'][0]['fallback_models'], ['two'])
