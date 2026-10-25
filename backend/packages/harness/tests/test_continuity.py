import unittest
from storyclaw.workflows.continuity import repetition_evidence
from storyclaw.agents.nodes.reviewer import reviewer
from storyclaw.context.writing_context import compose_context
from unittest.mock import patch,AsyncMock

class ContinuityTests(unittest.IsolatedAsyncioTestCase):
 def test_reused_transaction_dialogue_warns_but_shared_names_do_not(self):
  passage='林婶攥着卷边账册，催她把这个月的灯油差数补上。沈照取出几枚磨亮的铜钱，说南段三号灯的油路堵塞，多耗的半两清油是疏通油路用的。'
  evidence=repetition_evidence('翌日，'+passage+'她踏上码头。','昨日，'+passage+'账已付清。')
  self.assertTrue(evidence['warning'])
  self.assertFalse(repetition_evidence('沈照在码头找老曲问路。','沈照在家修灯，林婶来访。')['warning'])
 async def test_previous_normal_chapter_is_supplied_in_full(self):
  previous='章首已经结清灯油账。'+'正文细节。'*200+'章末发现碎片。'
  with patch('storyclaw.context.writing_context.query_context',AsyncMock(return_value={'chunks':[],'relations':[]})):
   ctx=await compose_context(user_id=1,book_id=2,book={},chapter={'number':2,'title':'追查'},outline={'volumes':[]},settings={},previous=previous,allowed=[1],chapter_numbers={1:1},scene_plan={},pending=[])
  self.assertEqual(ctx['recent_chapter_text'],previous);self.assertFalse(ctx['recent_chapter_truncated'])
 async def test_reviewer_reports_repeated_passages_without_claiming_semantic_proof(self):
  paragraph='账房翻出昨夜的旧册，指着同一笔已经付清的灯油款，命令她重新交钱。沈照又一次取出三枚铜钱，重复说明修灯清油的来路。'
  out=await reviewer({'draft_content':paragraph,'context':{'recent_chapter_text':paragraph,'chapter_meta':{'per_chapter_words':100}},'review_round':0})
  self.assertEqual(out['status'],'review_retry');self.assertIn('跨章重复',out['review_feedback'])
