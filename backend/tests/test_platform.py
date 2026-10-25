"""Integration test against a disposable, explicitly named PostgreSQL database.

DATABASE_URL=postgresql+asyncpg://.../storyclaw_refactor_test \
PYTHONPATH=backend:packages/storyclaw/src python -m unittest discover -s backend/tests -v
"""
import asyncio
import os
import unittest
from uuid import uuid4
from unittest.mock import patch
import httpx
from sqlalchemy import select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine

class PlatformIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_platform_workflow(self):
        url = os.environ.get('DATABASE_URL', '')
        if not url.endswith('/storyclaw_refactor_test'):
            self.skipTest('Requires disposable storyclaw_refactor_test database')
        import app.database as database
        await database.engine.dispose()
        database.engine = create_async_engine(url, poolclass=NullPool)
        database.AsyncSessionLocal.configure(bind=database.engine)
        from app.main import app
        from app.models import Base, User
        from app.models.platform import PlatformEvent
        from app.services.configs import _snapshot
        from app.services.credits import debit
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _snapshot.clear()
        suffix = uuid4().hex[:8]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            self.assertEqual((await c.get('/api/v1/admin/overview')).status_code, 401)
            user = f'writer_{suffix}'
            registered = await c.post('/api/v1/auth/register', json={'username':user,'password':'test123456','version':'local','is_admin':True})
            self.assertEqual(registered.status_code, 200, registered.text)
            self.assertNotIn('token', registered.json())
            self.assertEqual(registered.json()['version'], 'business')
            self.assertFalse(registered.json()['is_admin'])
            uid = registered.json()['id']
            login = await c.post('/api/v1/auth/login', json={'username':user,'password':'test123456'})
            headers = {'Authorization':f'Bearer {login.json()["token"]}'}
            self.assertEqual((await c.get('/api/v1/admin/overview',headers=headers)).status_code,403)
            async with database.AsyncSessionLocal() as db:
                u = await db.get(User,uid);u.is_admin=True;await db.commit()
            self.assertTrue((await c.get('/api/v1/auth/me',headers=headers)).json()['is_admin'])
            self.assertEqual((await c.get('/api/v1/admin/overview',headers=headers)).status_code,200)
            payload={'models':[{'id':'platform-test','display_name':'测试模型','format':'openai_chat','model':'upstream-test','base_url':'https://example.com/v1','enabled':True,'api_key':'secret-test-key'}]}
            result=await c.put('/api/v1/admin/models',json=payload,headers=headers)
            self.assertEqual(result.status_code,200,result.text)
            admin_models=await c.get('/api/v1/admin/models',headers=headers)
            self.assertNotIn('secret-test-key',admin_models.text)
            self.assertNotIn('api_key_enc',admin_models.text)
            self.assertTrue(admin_models.json()['models'][0]['has_key'])
            public=await c.get('/api/v1/models',headers=headers)
            self.assertNotIn('secret-test-key',public.text)
            self.assertNotIn('api_key_enc',public.text)
            # Read-only config directory does not prevent model/pricing updates.
            pricing={'pricing':{'platform-test':{'input_price':1,'output_price':2,'enabled':True}},'defaults':{'free_quota':0}}
            self.assertEqual((await c.put('/api/v1/admin/pricing',headers=headers,json=pricing)).status_code,200)
            from app.services.llm import _build_business
            with patch('app.services.llm.build_chat_client',return_value=object()) as build:
                _, mid = _build_business('platform-test')
                self.assertEqual(mid,'platform-test')
                self.assertEqual(build.call_args.kwargs['model'],'upstream-test')
                self.assertEqual(build.call_args.kwargs['api_key'],'secret-test-key')
            payload['models'][0]['enabled']=False
            self.assertEqual((await c.put('/api/v1/admin/models',headers=headers,json=payload)).status_code,400)
            before=(await c.get('/api/v1/auth/me',headers=headers)).json()['credits_balance']
            request={'delta':10,'reason':'测试发放','request_id':str(uuid4())}
            for _ in range(2):
                self.assertEqual((await c.post(f'/api/v1/admin/users/{uid}/credits',headers=headers,json=request)).status_code,200)
            after=(await c.get('/api/v1/auth/me',headers=headers)).json()['credits_balance']
            self.assertEqual(after,before+10)
            request['delta']=20
            self.assertEqual((await c.post(f'/api/v1/admin/users/{uid}/credits',headers=headers,json=request)).status_code,409)
            async def charge():
                async with database.AsyncSessionLocal() as db:
                    u=await db.get(User,uid)
                    await debit(db,u,1);await db.commit()
            await asyncio.gather(*(charge() for _ in range(5)))
            self.assertEqual((await c.get('/api/v1/auth/me',headers=headers)).json()['credits_balance'],after-5)
            request={'delta':-1000000,'reason':'超额扣除','request_id':str(uuid4())}
            self.assertEqual((await c.post(f'/api/v1/admin/users/{uid}/credits',headers=headers,json=request)).status_code,400)
            self.assertEqual((await c.get(f'/api/v1/admin/users/{uid}',headers=headers)).status_code,200)
            logs=await c.get('/api/v1/admin/logs',headers=headers)
            self.assertEqual(logs.status_code,200)
            self.assertTrue(any(x['action']=='credits.adjust' for x in logs.json()))
            self.assertNotIn('secret-test-key',logs.text)
            self.assertEqual((await c.post('/api/v1/recharge/purchase',headers=headers,json={'membership_id':'monthly'})).status_code,503)
            self.assertEqual((await c.get('/api/v1/llm-configs',headers=headers)).status_code,404)
            # Config is recovered from the database after a process-cache reset.
            _snapshot.clear()
            catalog=await c.get('/api/v1/models',headers=headers)
            self.assertEqual(catalog.json()[0]['id'],'platform-test')
        await database.engine.dispose()
