import unittest
from unittest.mock import AsyncMock,patch
from storyclaw.contracts import ManuscriptReference
from app.services.agent.manuscript_references import resolve_reference,replace_range
from storyclaw.workflows.continuity import prose

class ManuscriptReferencesTests(unittest.TestCase):
 def reference(self,kind,offset,text='',affinity='after'):
  return ManuscriptReference(kind=kind,chapter_id=1,title='第一章',line_start=1,line_end=2,
      text=text,offset=offset,expected_hash='a'*64,affinity=affinity)

 def test_duplicate_selection_resolves_the_attached_occurrence(self):
  html='<p>夜雨落下。</p><p>夜雨落下。</p>'
  span=resolve_reference(html,self.reference('selection',5,'夜雨落下。'))
  result=replace_range(html,span['start'],span['end'],'天光初现。')
  self.assertEqual(result,'<p>夜雨落下。</p><p>天光初现。</p>')

 def test_cross_paragraph_selection_preserves_unaffected_formatting(self):
  html='<h2>标题</h2><p><strong>角色甲</strong>走进屋里。</p><p>他点亮灯。</p><p><em>后文保留。</em></p>'
  span=resolve_reference(html,self.reference('selection',5,'走进屋里。\n他点亮灯。'))
  result=replace_range(html,span['start'],span['end'],'推门进屋，点亮灯火。')
  self.assertIn('<h2>标题</h2>',result);self.assertIn('<strong>角色甲</strong>',result)
  self.assertIn('<em>后文保留。</em>',result)
  self.assertEqual(prose(result),'标题角色甲推门进屋，点亮灯火。后文保留。')

 def test_cursor_inserts_between_existing_content_instead_of_appending(self):
  html='<p><strong>夜雨</strong>落下。</p><p>后文。</p>'
  span=resolve_reference(html,self.reference('cursor',2))
  result=replace_range(html,span['start'],span['end'],'忽然停了，')
  self.assertEqual(prose(result),'夜雨忽然停了，落下。后文。')
  self.assertIn('<p>后文。</p>',result)

 def test_unicode_entities_whitespace_and_repeated_text(self):
  html='<p>😀 甲&amp;乙</p><p>甲乙</p>'
  span=resolve_reference(html,self.reference('selection',4,'甲\n乙'))
  self.assertEqual(span['text'],'甲乙')
  self.assertEqual(prose(replace_range(html,span['start'],span['end'],'丙丁')),'😀 甲&乙丙丁')

 def test_stale_or_fabricated_range_is_rejected(self):
  with self.assertRaises(ValueError):resolve_reference('夜雨落下。',self.reference('selection',2,'完全不同的片段'))
  with self.assertRaises(ValueError):resolve_reference('正文',self.reference('cursor',100))

 def test_replacement_never_executes_model_markup(self):
  result=replace_range('<p>甲乙</p>',0,1,'<script>alert(1)</script>')
  self.assertNotIn('<script>',result);self.assertIn('&lt;script&gt;',result)

class ContinuationContextTests(unittest.IsolatedAsyncioTestCase):
 async def test_full_chapter_and_author_goal_reach_writer_even_at_first_cursor(self):
  from storyclaw.agents.nodes.writer import _writer_continue
  full='开头原文。'+('中间原文。'*400)+'本章结尾标记。'
  state={'context':{'cursor_offset':0,'continuation_suffix':full,'author_instruction':'在章首补一个短场景'},'current_content':full,'prefix_text':''}
  with patch('storyclaw.agents.nodes.writer._respond_aware',AsyncMock(return_value=('新句。',0,0,'fake'))) as respond:
   await _writer_continue(state)
  system=respond.call_args.args[1]
  self.assertIn(full,system);self.assertIn('在章首补一个短场景',system)
