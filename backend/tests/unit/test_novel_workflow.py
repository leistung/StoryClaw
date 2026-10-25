import ast
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,MagicMock,patch
from storyclaw.context.writing_context import compose_context
from storyclaw.rag.service import _extract_entities_llm
from storyclaw.workflows.workflow import pending_history
from storyclaw.agents.nodes.writer import _writer_write

class NovelWorkflowTests(unittest.IsolatedAsyncioTestCase):
 async def test_context_cites_chapter_number_and_world_rules_and_errors(self):
  lookup=AsyncMock(return_value={'chunks':[{'chapter_id':92,'text':'旧约定'}],'relations':[],'error':'图库暂不可用'})
  with patch('storyclaw.context.writing_context.query_context',lookup):
   context=await compose_context(user_id=2,book_id=3,book={'intro':'简介'},chapter={'id':93,'number':2,'title':'新约'},outline={'volumes':[]},settings={'world':[{'name':'规则','category':'限制','description':'法术必有代价','extra_json':None}]},previous='上一章结尾',allowed=[92],chapter_numbers={92:1},scene_plan={},pending=[])
  self.assertIn('第1章 / 来源ID 92',context['rag_briefs'])
  self.assertIn('法术必有代价',context['setting_briefs']['world'])
  self.assertEqual(lookup.call_args.kwargs['allowed_chapter_ids'],[92])
  result=await _writer_write({'context':context})
  self.assertEqual(result['status'],'error');self.assertEqual(result['draft_content'],'')
 async def test_entity_extraction_includes_late_chapter_and_deduplicates(self):
  extract=AsyncMock(return_value=([{'name':'甲','type':'character','description':'守护小店'}],[{'from':'甲','to':'小店','type':'owns'}]))
  text='首'+('文'*8500)+'尾章关键事实'
  with patch('storyclaw.rag.service._extract_segment',extract):entities,relations=await _extract_entities_llm(text,{})
  self.assertGreater(extract.await_count,1)
  self.assertIn('尾章关键事实',''.join(c.args[0] for c in extract.call_args_list))
  self.assertEqual(len(entities),1);self.assertEqual(len(relations),1)
 async def test_store_query_failure_is_not_silently_empty_memory(self):
  vector=MagicMock();vector.available=True;vector.search.side_effect=RuntimeError('connection closed')
  graph=MagicMock();graph.available=True
  with patch('storyclaw.rag.service._milvus',vector),patch('storyclaw.rag.service._neo4j',graph),patch('storyclaw.rag.service._resolve_embed_cfg',AsyncMock(return_value=None)),patch('storyclaw.rag.service.embedding.embed_query',AsyncMock(return_value=[0.1])):
   from storyclaw.rag.service import query_context
   result=await query_context(1,2,'小店',allowed_chapter_ids=[1])
  self.assertTrue(result['error']);self.assertEqual(result['chunks'],[])
 def test_only_written_unindexed_history_blocks_next_chapter(self):
  self.assertEqual(pending_history([{'number':1,'word_count':20,'rag_status':'pending'},{'number':2,'word_count':0,'rag_status':'pending'},{'number':3,'word_count':20,'rag_status':'loaded'}]),[1])
 def test_ai_package_has_no_backend_or_http_database_imports(self):
  root=Path(__file__).resolve().parents[2]/'packages/harness/storyclaw'
  self.assertTrue(root.is_dir(), str(root))
  self.assertGreater(len(list(root.rglob('*.py'))), 20)
  for path in root.rglob('*.py'):
   for node in ast.walk(ast.parse(path.read_text())):
    imports=[n.name for n in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
    for name in imports:self.assertNotIn(name.split('.')[0],{'backend','app','fastapi','sqlalchemy'},str(path))

 def test_backend_has_no_direct_model_or_graph_inference(self):
  root=Path(__file__).resolve().parents[2]/'app'
  self.assertTrue(root.is_dir(), str(root))
  self.assertGreater(len(list(root.rglob('*.py'))), 20)
  for path in root.rglob('*.py'):
   for node in ast.walk(ast.parse(path.read_text())):
    if isinstance(node,ast.ImportFrom):
     self.assertFalse((node.module or '').startswith(('langchain','langgraph')),str(path))
     self.assertFalse((node.module or '')=='storyclaw.models.calls' and any(n.name in {'llm_respond','stream_llm_respond'} for n in node.names),str(path))
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
     self.assertNotIn(node.func.attr,{'ainvoke','astream'},str(path))
