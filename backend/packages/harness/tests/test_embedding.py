import unittest
from unittest.mock import patch
import httpx
from storyclaw.rag import embedding

class EmbeddingValidation(unittest.IsolatedAsyncioTestCase):
    async def call(self, items):
        client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'data': items}))
        with patch.object(embedding.settings, 'milvus_dim', 2), patch.object(embedding.httpx, 'AsyncClient', side_effect=lambda **kw: client(transport=transport, **kw)), patch.dict('os.environ', {'EMBEDDING_MODE': ''}):
            return await embedding.embed_texts(['first','second'], {'model':'test','base_url':'https://example.test/v1','api_key':'test'})

    async def test_results_reordered_by_input_index(self):
        self.assertEqual(await self.call([{'index':1,'embedding':[0,1]},{'index':0,'embedding':[1,0]}]), [[1,0],[0,1]])

    async def test_reject_dimension_mismatch(self):
        with self.assertRaisesRegex(ValueError, '维度'):
            await self.call([{'index':0,'embedding':[1]},{'index':1,'embedding':[0,1]}])

    async def test_reject_missing_result(self):
        with self.assertRaisesRegex(ValueError, '数量'):
            await self.call([{'index':0,'embedding':[1,0]}])

    async def test_reject_non_finite_vector(self):
        # Strings and non-numeric provider output must also be rejected.
        with self.assertRaisesRegex(ValueError, '数值'):
            await self.call([{'index':0,'embedding':['NaN',0]},{'index':1,'embedding':[0,1]}])

    async def test_custom_dimensions_sent_to_provider(self):
        import json
        captured = []
        def respond(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={'data':[{'index':0,'embedding':[1,0]}]})
        client = httpx.AsyncClient
        transport = httpx.MockTransport(respond)
        with patch.object(embedding.settings, 'milvus_dim', 2), patch.object(embedding.httpx, 'AsyncClient', side_effect=lambda **kw: client(transport=transport, **kw)), patch.dict('os.environ', {'EMBEDDING_MODE':''}):
            await embedding.embed_texts(['test'], {'model':'embedding-3','base_url':'https://example.test/v4','api_key':'test','dimensions':2})
        self.assertEqual(captured[0]['dimensions'], 2)
