import json
import unittest
from unittest.mock import AsyncMock, patch
from storyclaw.workflows.creation_plan import CreationPlan
from storyclaw.workflows.creation_plan import propose_plan
from storyclaw.workflows.serial import generate_framework
from storyclaw.workflows.design import generate_design
from storyclaw.agents.lead_agent.agent import StoryClaw

class CreationPlanTests(unittest.IsolatedAsyncioTestCase):
 async def test_planning_uses_the_relevant_method_without_extra_model_calls(self):
  expected={'outline':'framework-design','character':'character-arc','world':'world-design','plot':'plot-design'}
  for kind,method in expected.items():
   with self.subTest(kind=kind):
    model=AsyncMock(return_value=(json.dumps(self.plan()),0,0,'fake'))
    with patch('storyclaw.workflows.creation_plan.llm_respond',model),patch('storyclaw.workflows.creation_plan.method_instructions',return_value='method-sentinel') as instructions:
     result=await propose_plan(kind,{'book_title':'既有作品'})
    instructions.assert_called_once_with(method)
    model.assert_awaited_once()
    self.assertIn('method-sentinel',model.call_args.args[1])
    self.assertEqual(json.loads(model.call_args.args[2])['kind'],kind)
    self.assertIsInstance(result,CreationPlan)

 def plan(self, count=2):
  return CreationPlan(goal='依据作品的商战冲突安排对手、盟友和关键资源，具体展开各阶段行动。',
      sections=[{'name':f'第{i+1}卷','brief':'主角争夺旧港经营权，经历资金危机后找到盟友，并在商会内部建立新的规则。'} for i in range(count)],
      item_count=count,detail_words=300).model_dump()

 async def test_framework_expands_every_approved_volume(self):
  model=AsyncMock(side_effect=[(json.dumps({'overview':'经营权之争推动人物成长。'*70}),0,0,'fake'),
      (json.dumps({'goal':'主角争取订单，遭遇对手封锁并付出代价。'*20}),0,0,'fake'),
      (json.dumps({'goal':'盟友参与经营，商会内部分裂并形成新局面。'*20}),0,0,'fake')])
  with patch('storyclaw.workflows.serial.llm_respond',model):
   result=await generate_framework({'planning_mode':'serial','creation_plan':self.plan()})
  self.assertEqual(len(result['volumes']),2)
  self.assertEqual([v['name'] for v in result['volumes']],['第1卷','第2卷'])
  self.assertEqual(model.await_count,3)
  self.assertTrue(all(len(v['goal'])>=180 for v in result['volumes']))

 async def test_underdeveloped_framework_is_rejected(self):
  with patch('storyclaw.workflows.serial.llm_respond',AsyncMock(return_value=('{"overview":"几句话"}',0,0,'fake'))):
   with self.assertRaisesRegex(ValueError,'展开不足'):await generate_framework({'creation_plan':self.plan()})

 async def test_dossiers_match_count_and_carry_previous_batch(self):
  def response(names):return json.dumps({'summary':'角色关系设计','dossiers':[{'name':name,'category':'盟友','description':'负责商会经营，面对资源竞争时必须作出有代价的选择。'*12} for name in names]},ensure_ascii=False),10,20,'fake'
  plan=self.plan();plan['item_count']=5
  model=AsyncMock(side_effect=[response(['甲','乙','丙']),response(['丁','戊'])])
  with patch('storyclaw.workflows.design.llm_respond',model):
   result,ins,outs,_=await generate_design('character',{}, {}, [],{},plan)
  self.assertEqual(len(result.dossiers),5);self.assertEqual((ins,outs),(20,40))
  self.assertEqual(len(json.loads(model.call_args_list[1].args[2])['generated']),3)

 async def test_tool_failures_emit_arguments_and_error(self):
  ports=type('Ports',(),{})();ports.emit=AsyncMock();ports.execute=AsyncMock(side_effect=ValueError('资料不存在'))
  with self.assertRaises(ValueError):await StoryClaw(ports).execute('memory.search',{'query':'旧港'})
  calls=ports.emit.call_args_list
  self.assertEqual(calls[0].args[1]['arguments'],{'query':'旧港'})
  self.assertEqual(calls[-1].args[0],'tool.failed')
  self.assertEqual(calls[-1].args[1]['error'],'资料不存在')
