import unittest
from unittest.mock import AsyncMock,patch
from pathlib import Path
from storyclaw.agent import StoryClaw
from storyclaw.contracts import AgentRequest,CapabilityResult,ModelTurn,ToolCall
from storyclaw.skills import read_skill_doc,read_skill_sections,list_skills,canonical_skill,describe_skill

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
  with patch('storyclaw.skills.settings.skills_path',Path('skills').resolve()):
   self.assertEqual(canonical_skill('write-chapter'),'chapter-craft')
   self.assertEqual(read_skill_doc('write-chapter'),read_skill_doc('chapter-craft'))
   self.assertIn('workflow',read_skill_sections('write-chapter'))
   self.assertEqual(read_skill_doc('../docs/archive/skills-v1/write-chapter'),'')
   names={s['name'] for s in list_skills()}
   self.assertEqual(len(names),11);self.assertNotIn('write-multi-chapters',names)
   self.assertFalse(describe_skill('write-multi-chapters')['available'])
