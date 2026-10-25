import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from storyclaw.models.calls import llm_respond
from storyclaw.models.calls import stream_llm_respond
class Client:
 def __init__(self):self.bound={}
 def bind(self,**kwargs):self.bound.update(kwargs);return self
 async def ainvoke(self,messages):return SimpleNamespace(content='{"reply":"好"}',usage_metadata={'input_tokens':1,'output_tokens':2})
 async def astream(self,messages):yield SimpleNamespace(content='{"reply":"好"}',usage_metadata={'input_tokens':1,'output_tokens':2})
class JSONModeTests(unittest.IsolatedAsyncioTestCase):
 async def test_json_constraint_forwarded_for_sync_and_stream(self):
  for invoke in (llm_respond,stream_llm_respond):
   client=Client()
   with patch('storyclaw.models.calls.get_llm',AsyncMock(return_value=(client,'test'))):
    result=await invoke({'response_format':{'type':'json_object'}},'Return JSON','提问')
   self.assertEqual(client.bound['response_format'],{'type':'json_object'})
   self.assertEqual(result[0],'{"reply":"好"}')
 async def test_other_calls_keep_original_format(self):
  client=Client()
  with patch('storyclaw.models.calls.get_llm',AsyncMock(return_value=(client,'test'))):await llm_respond({},'写小说','开始')
  self.assertNotIn('response_format',client.bound)
