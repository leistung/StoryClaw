"""Long-form provenance, budgets, isolation and recovery against synthetic manuscripts."""
import os,unittest,io,zipfile
from uuid import uuid4
from unittest.mock import AsyncMock,patch
from storyclaw.workflows.library import decode_manuscript,split_manuscript
class ManuscriptParser(unittest.TestCase):
 def test_encodings_and_original_numbers(self):
  text='第1章 开始\n主角发现一盏灯。\n第3章 失踪\n主角发现一盏灯。'
  for encoding in ('utf-8-sig','utf-16','gb18030'):
   parts,warnings=split_manuscript(decode_manuscript('test.txt',text.encode(encoding)))
   self.assertEqual(len(parts),2);self.assertEqual(parts[1]['number'],2);self.assertEqual(len(warnings),2)
 def test_docx_and_bad_input(self):
  buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>第1章 灯</w:t></w:r></w:p><w:p><w:r><w:t>灯亮了。</w:t></w:r></w:p></w:document>')
  self.assertIn('灯亮了',decode_manuscript('test.docx',buf.getvalue()))
  with self.assertRaises(ValueError):decode_manuscript('test.exe',b'abc')
 def test_five_million_words(self):
  text='\n'.join(f'第{i}章 灯火\n'+('灯火照亮归途。'*400) for i in range(1,1801))
  parts,_=split_manuscript(text)
  self.assertEqual(len(parts),1800);self.assertGreater(sum(p['words'] for p in parts),5000000)
class StudioIntegration(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  if not os.environ.get('DATABASE_URL','').endswith('/storyclaw_refactor_test'):self.skipTest('isolated DB only')
  import app.database as database
  from sqlalchemy.ext.asyncio import create_async_engine
  from sqlalchemy.pool import NullPool
  await database.engine.dispose();database.engine=create_async_engine(os.environ['DATABASE_URL'],poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base,User
  import httpx
  self.db=database.AsyncSessionLocal
  async with database.engine.begin() as c:await c.run_sync(Base.metadata.create_all)
  self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test/api/v1')
  name='studio'+uuid4().hex[:8]
  await self.client.post('/auth/register',json={'username':name,'password':'test123456'})
  r=(await self.client.post('/auth/login',json={'username':name,'password':'test123456'})).json()
  self.uid=r['user']['id'];self.client.headers['Authorization']='Bearer '+r['token']
  async with self.db() as db:
   u=await db.get(User,self.uid);u.credits_balance=10000;await db.commit()
  self.bid=(await self.req('POST','/books',{'title':'合成测试长篇','genre':'玄幻'}))['id']
 async def asyncTearDown(self):
  if hasattr(self,'client'):await self.client.aclose()
 async def req(self,method,path,body=None,status=200):
  r=await self.client.request(method,path,json=body);self.assertEqual(r.status_code,status,r.text);return r.json()
 async def upload(self):
  r=await self.client.post(f'/books/{self.bid}/sources',files={'file':('own.txt','第1章 归来\n甲带着旧灯回村。\n第2章 秘密\n甲不知道灯藏着秘密。'.encode(),'text/plain')},data={'read_allowed':'true','ai_allowed':'true','basis':'own','commercial_allowed':'true'})
  self.assertEqual(r.status_code,200,r.text);return r.json()
 async def test_source_baseline_branch_cutoff_and_revoke(self):
  from app.services.library import reference_context,imported_exemptions
  from app.models import Chapter
  from sqlalchemy import select
  source=await self.upload();sid=source['id']
  data={'source_id':sid,'file_hash':source['file_hash'],'mode':'takeover','cutoff':2,'notes':'甲已经回到故乡，带着旧灯，不知道灯中的秘密。接下来探查失踪事件。'}
  baseline=await self.req('POST',f'/books/{self.bid}/baseline/confirm',data);self.assertEqual(baseline['status'],'assisted_ready')
  async with self.db() as db:
   self.assertEqual(len(await imported_exemptions(db,self.bid)),2)
  branch=(await self.req('POST','/books',{'title':'独立分支','genre':'玄幻'}))['id']
  await self.req('POST',f'/books/{branch}/baseline/confirm',{**data,'mode':'derivative','cutoff':1})
  async with self.db() as db:
   ctx=await reference_context(db,self.uid,branch,'秘密');self.assertTrue(all(e['source_chapter']<=1 for e in ctx['evidence']))
   self.assertIsNone(await db.scalar(select(Chapter.id).where(Chapter.book_id==branch)))
  await self.req('POST',f'/sources/{sid}/revoke')
  async with self.db() as db:
   from fastapi import HTTPException
   with self.assertRaises(HTTPException):await reference_context(db,self.uid,branch,'')
 async def test_analysis_checkpoint_and_resume(self):
  from app.services.studio_tasks import poll_once
  from app.models.studio import SourceChapter
  from sqlalchemy import select
  s=await self.upload()
  task=await self.req('POST',f'/books/{self.bid}/plans',{'kind':'source-analysis','source_id':s['id'],'start':1,'end':2,'budget':100})
  digest={'summary':'甲回到村庄，带着一盏灯，不知道灯中的秘密。','facts':[],'unresolved':[],'uncertainties':[]}
  with patch('storyclaw.workflows.library.analyze_source_chapter',AsyncMock(return_value=(digest,20,30,'mock'))),patch('storyclaw.workflows.library.index_source_segment',AsyncMock(return_value={'chunks':1,'stores':{'vector':'milvus','graph':'neo4j'}})):
   await poll_once(task['id']);await poll_once(task['id']);await poll_once(task['id'])
  plans=await self.req('GET',f'/books/{self.bid}/plans');self.assertEqual(plans[0]['status'],'succeeded')
  async with self.db() as db:
   rows=list(await db.scalars(select(SourceChapter).where(SourceChapter.source_id==s['id'])));self.assertTrue(all(r.analysis_status=='ready' for r in rows))
  await self.req('POST',f'/plans/{task["id"]}/control',{'action':'resume'},status=409)
 async def test_release_snapshot_methods_and_permissions(self):
  c=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'第一章'})
  await self.req('PUT',f'/chapters/{c["id"]}',{'content':'<p>旧版本故事。</p>'})
  await self.req('POST',f'/books/{self.bid}/releases',{'platform':'测试平台'},status=422)
  release=await self.req('POST',f'/books/{self.bid}/releases',{'platform':'测试平台','rights_confirmed':True,'ai_policy_confirmed':True})
  await self.req('PUT',f'/chapters/{c["id"]}',{'content':'<p>全新故事。</p>'})
  r=await self.client.get(f'/releases/{release["id"]}/export');self.assertEqual(r.status_code,200,r.text if r.status_code!=200 else '')
  with zipfile.ZipFile(io.BytesIO(r.content)) as z:
   text=z.read('manuscript.txt').decode();self.assertIn('旧版本故事',text);self.assertNotIn('全新故事',text)
  await self.req('POST',f'/releases/{release["id"]}/receipt',{'status':'submitted','snapshot_hash':'0'*64},status=409)
  await self.req('POST',f'/releases/{release["id"]}/receipt',{'status':'submitted','snapshot_hash':release['hash']})
  m=await self.req('POST','/private-methods',{'title':'简洁','content':'对白保持简洁，通过行动表现人物。'})
  await self.req('PUT',f'/private-methods/{m["id"]}',{'title':'简洁','content':'对白保持简洁，通过行动表现人物。','enabled':True})
  await self.req('DELETE',f'/private-methods/{m["id"]}')
 async def test_meter_reserved_cap_refund_and_plan_budget(self):
  from app.services.metering import usage_scope
  from app.models import User
  from app.models.studio import StudioTask
  from fastapi import HTTPException
  task=await self.req('POST',f'/books/{self.bid}/plans',{'kind':'serial','budget':1})
  async with usage_scope(self.uid,plan_id=task['id']) as meter:
   with self.assertRaises(HTTPException):await meter.reserve('embedding:test',5000,0)
   cid=await meter.reserve('embedding:test',100,0)
   with patch('app.services.configs.load_pricing',return_value={'defaults':{'embedding_credits_per_1k':2000}}):
    self.assertEqual(await meter.settle(cid,{'input_tokens':100},True),1)
   with self.assertRaises(HTTPException):await meter.reserve('embedding:test',100,0)
  async with self.db() as db:
   self.assertEqual((await db.get(StudioTask,task['id'])).spent,1);self.assertEqual((await db.get(User,self.uid)).credits_balance,9999)
 async def test_manifest_failed_stage_not_visible(self):
  from app.services.index_manifest import stage,activate,resolve
  from app.models import Chapter
  from app.services.revisions import chapter_hash
  c=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'章'})
  async with self.db() as db:
   row=await db.get(Chapter,c['id']);row.content='测试正文';row.word_count=4;h=chapter_hash(row)
   manifest=await stage(db,row,h)
   self.assertFalse(await activate(db,manifest,row,{'chunks':2,'stores':{'vector':'milvus','graph':'memory'}},h));await db.commit()
  self.assertEqual(await resolve(self.uid,self.bid),{})
  async with self.db() as db:
   row=await db.get(Chapter,c['id']);manifest=await stage(db,row,h)
   self.assertTrue(await activate(db,manifest,row,{'chunks':2,'stores':{'vector':'milvus','graph':'neo4j'}},h));row.rag_status='loaded';physical=manifest.physical_id;await db.commit()
  self.assertEqual(await resolve(self.uid,self.bid),{physical:c['id']})
 async def test_twelve_chapters_rolling_plan_complete(self):
  from app.services.studio_tasks import serial_step
  from app.services.jobs import run_job
  from app.models.studio import StudioTask
  from app.models.product import WorkJob
  from app.models import Chapter
  from storyclaw.serial import Blueprint
  from sqlalchemy import select
  frame={'planning_mode':'serial','overview':'河灯匠逐步追查失踪的父亲，在雾港守护邻人和灯火，长期悬念保持开放，不锁定总章节数量。','volumes':[{'name':'寻灯','goal':'调查灯印与失踪事件，逐步确定后续方向，不提前结束长期故事。','chapters':[]}]}
  await self.req('PUT',f'/books/{self.bid}/outline',{'content':frame});await self.req('POST',f'/books/{self.bid}/outline/confirm',{'content':frame})
  task=await self.req('POST',f'/books/{self.bid}/plans',{'kind':'serial','start':1,'end':12,'budget':100,'auto_adopt':True})
  count=0
  async def blueprint(*args):
   nonlocal count
   count+=1
   return Blueprint(title=f'灯印{count}',summary=f'河灯匠沿着第{count}条灯印寻找失踪父亲，每次揭示新线索而不重演前文，保持父亲下落未定。',constraints=['父亲仍失踪']),1,1,'mock'
  async def agent(*args,**kwargs):
   return {'draft_content':f'第{count}次调查。'+('灯匠沿着潮水留下的痕迹慢慢向前走，街坊记得那天的风雨。'*100),'token_usage':{}}
  result={'chunks':3,'entities':1,'relations':0,'stores':{'vector':'milvus','graph':'neo4j'},'error':None}
  with patch('app.services.serial.generate_blueprint',side_effect=blueprint),patch('app.services.chat_workflow.run_agent',side_effect=agent),patch('app.services.pricing.compute_cost',return_value=1),patch('storyclaw.writing_context.query_context',AsyncMock(return_value={'chunks':[],'entities':[],'relations':[]})),patch('app.services.knowledge_workflow.rag_svc.ingest_text',AsyncMock(return_value=result)):
   for _ in range(80):
    await serial_step(task['id'])
    async with self.db() as db:
     t=await db.get(StudioTask,task['id']);status=t.status;jid=t.current_job
     j=await db.get(WorkJob,jid) if jid else None
    if status=='succeeded':break
    self.assertIn(status,('queued','running'),t.error)
    if j and j.status=='queued':await run_job(jid)
  self.assertEqual(status,'succeeded')
  async with self.db() as db:
   rows=list(await db.scalars(select(Chapter).where(Chapter.book_id==self.bid)))
   self.assertEqual(len(rows),12);self.assertTrue(all(c.rag_status=='loaded' for c in rows));self.assertGreater(sum(c.word_count for c in rows),25000)
 async def test_candidate_adoption_is_version_checked_and_idempotent(self):
  from app.models.agent import AgentRun
  c=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'章'})
  c=await self.req('PUT',f'/chapters/{c["id"]}',{'content':'<p>甲走进村庄。</p>'})
  rid=str(uuid4())
  async with self.db() as db:
   db.add(AgentRun(id=rid,user_id=self.uid,request_id=str(uuid4()),fingerprint='x'*64,request={'scope':{'book_id':self.bid,'chapter_id':c['id']}},status='succeeded',event_seq=0,credits_cost=0,reserved=0,result={'content':'甲提着灯，走进村庄。','data':{'artifact':True,'kind':'text.polish','chapter_id':c['id'],'selected_text':'甲走进村庄。','base_hash':c['content_hash']}}));await db.commit()
  await self.req('POST',f'/agent/runs/{rid}/adopt',{'expected_hash':'0'*64},status=409)
  await self.req('POST',f'/agent/runs/{rid}/adopt',{'expected_hash':c['content_hash']})
  await self.req('POST',f'/agent/runs/{rid}/adopt',{'expected_hash':c['content_hash']},status=409)
  updated=await self.req('GET',f'/chapters/{c["id"]}');self.assertIn('甲提着灯',updated['content']);self.assertEqual(updated['rag_status'],'pending')
 async def test_deletion_keeps_shared_source_and_deletes_unshared_tree(self):
  source=await self.upload()
  branch=(await self.req('POST','/books',{'title':'来源分支','genre':'玄幻'}))['id']
  await self.req('POST',f'/books/{branch}/baseline/confirm',{'source_id':source['id'],'file_hash':source['file_hash'],'mode':'derivative','cutoff':1,'notes':'甲刚回到村庄，不知道旧灯的秘密，本分支从此开始独立发展，不继承后续事件。'})
  await self.req('DELETE',f'/books/{self.bid}',status=409)
  await self.req('DELETE',f'/books/{branch}')
  c=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'待清理章节'})
  await self.req('PUT',f'/chapters/{c["id"]}',{'content':'已保存版本正文。'})
  await self.req('DELETE',f'/books/{self.bid}')
  await self.req('GET',f'/sources/{source["id"]}',status=404)
