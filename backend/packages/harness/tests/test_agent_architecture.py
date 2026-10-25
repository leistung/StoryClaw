import unittest
from unittest.mock import AsyncMock,patch
from pathlib import Path
from storyclaw.agents.lead_agent.agent import StoryClaw
from storyclaw.contracts import AgentRequest
from storyclaw.contracts import CapabilityResult
from storyclaw.contracts import ModelTurn
from storyclaw.contracts import ToolCall
from storyclaw.skills.loader import read_skill_doc
from storyclaw.skills.loader import read_skill_sections
from storyclaw.skills.loader import list_skills
from storyclaw.skills.loader import canonical_skill
from storyclaw.skills.loader import describe_skill

class AgentArchitectureTests(unittest.IsolatedAsyncioTestCase):
 async def test_command_and_chat_share_the_same_executor(self):
  ports=type('Ports',(),{})();ports.emit=AsyncMock();ports.execute=AsyncMock(return_value=CapabilityResult(status='waiting_task',content='queued',data={'job_id':'j1'}))
  ports.model_turn=AsyncMock(return_value=ModelTurn(calls=[ToolCall(name='chapter__plan')]))
  agent=StoryClaw(ports)
  command=AgentRequest(request_id='a'*16,entry='command',command='chapter.plan')
  result=await agent.run(command)
  self.assertEqual(result.status,'waiting_task');ports.model_turn.assert_not_called()
  result=await agent.run(AgentRequest(request_id='b'*16,message='规划本章'))
  self.assertEqual(result.status,'waiting_task');self.assertEqual(ports.execute.call_args_list[0],ports.execute.call_args_list[1])
  self.assertEqual(ports.model_turn.await_count,1)  # no model-based polling

 async def test_confirmations_are_not_exposed_as_model_capabilities(self):
  ports=type('Ports',(),{})();ports.emit=AsyncMock();ports.execute=AsyncMock()
  with self.assertRaises(ValueError):await StoryClaw(ports).execute('framework.confirm',{})
  ports.execute.assert_not_called()
  with self.assertRaises(ValueError):await StoryClaw(ports).execute('chapter.plan',{'user_id':2})
  ports.execute.assert_not_called()

 async def test_repeated_tools_stop_without_unbounded_calls(self):
  ports=type('Ports',(),{})();ports.emit=AsyncMock();ports.execute=AsyncMock(return_value=CapabilityResult(content='missing'))
  ports.model_turn=AsyncMock(return_value=ModelTurn(calls=[ToolCall(name='project__status')]))
  result=await StoryClaw(ports).run(AgentRequest(request_id='c'*16,message='继续'))
  self.assertEqual(result.status,'partial');self.assertEqual(ports.execute.await_count,2)

 def test_legacy_aliases_resolve_methods_without_exposing_archives(self):
  with patch('storyclaw.skills.loader.settings.skills_dir',str(Path(__file__).resolve().parents[1]/'storyclaw/skills/resources')):
   self.assertEqual(canonical_skill('write-chapter'),'chapter-craft')
   self.assertEqual(read_skill_doc('write-chapter'),read_skill_doc('chapter-craft'))
   self.assertIn('workflow',read_skill_sections('write-chapter'))
   self.assertEqual(read_skill_doc('../docs/archive/skills-v1/write-chapter'),'')
   names={s['name'] for s in list_skills()}
   self.assertEqual(len(names),11);self.assertNotIn('write-multi-chapters',names)
   self.assertFalse(describe_skill('write-multi-chapters')['available'])

 def test_history_filter_runs_before_vector_top_k(self):
  from storyclaw.rag.memory_store import MemoryVectorStore
  store=MemoryVectorStore()
  # Future chapters dominate the nearest hits; valid history must still be recalled.
  store._chunks[(1,2)]=[{'chapter_id':9,'embedding':[1.,0.],'text':'future'} for _ in range(50)]+[{'chapter_id':1,'embedding':[0.8,0.2],'text':'valid history'}]
  result=store.search(1,2,[1.,0.],1,allowed_chapter_ids=[1])
  self.assertEqual([c['chapter_id'] for c in result],[1])

 def test_milvus_filter_is_a_query_predicate(self):
  from unittest.mock import MagicMock
  from storyclaw.rag.milvus_store import MilvusStore
  store=MilvusStore();collection=MagicMock();collection.search.return_value=[[]]
  with patch.object(store,'_ensure_collection',return_value=collection):
   store.search(1,2,[.1],5,allowed_chapter_ids=[2,7])
  self.assertEqual(collection.search.call_args.kwargs['expr'],'chapter_id in [2,7]')

 async def test_partial_tool_json_never_executes(self):
  from langchain_core.messages import AIMessageChunk
  from storyclaw.orchestration.model import generate_lead_turn
  class Fake:
   def bind_tools(self,tools):return self
   def bind(self,**kwargs):return self
   async def astream(self,msgs):
    yield AIMessageChunk(content='',tool_call_chunks=[{'name':'chapter__write','args':'{"prompt":','id':'bad','index':0}],response_metadata={'finish_reason':'length'})
  with self.assertRaises(ValueError):await generate_lead_turn(Fake(),[{'role':'user','content':'write'}],[],AsyncMock(),AsyncMock())

 async def test_facade_exposes_live_execution_without_a_global_user(self):
  ports=type('Ports',(),{})();ports.emit=AsyncMock();ports.execute=AsyncMock(return_value=CapabilityResult(content='status ok'))
  events=[event async for event in StoryClaw(ports).stream(AgentRequest(request_id='d'*16,entry='command',command='project.status'))]
  self.assertEqual(events[-1]['type'],'run.completed')
  self.assertEqual(events[-1]['payload']['content'],'status ok')
