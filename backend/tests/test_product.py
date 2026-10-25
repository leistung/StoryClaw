"""Cross-user product flows against an explicitly isolated PostgreSQL database."""
import os,unittest
from uuid import uuid4
from unittest.mock import patch,AsyncMock
import httpx
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import select

class ProductIntegration(unittest.IsolatedAsyncioTestCase):
 async def test_product_flows(self):
  url=os.environ.get('DATABASE_URL','')
  if not url.endswith('/storyclaw_refactor_test'):self.skipTest('Requires isolated product test database')
  import app.database as database
  await database.engine.dispose();database.engine=create_async_engine(url,poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base,User,Chapter
  from app.models.product import WorkJob
  from app.services.configs import _snapshot
  async with database.engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
  _snapshot.clear()
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
   async def signup(prefix):
    name=prefix+uuid4().hex[:8]
    response=await client.post('/api/v1/auth/register',json={'username':name,'password':'test123456'})
    self.assertEqual(response.status_code,200,response.text)
    login=(await client.post('/api/v1/auth/login',json={'username':name,'password':'test123456'})).json()
    return login['user']['id'],{'Authorization':'Bearer '+login['token']}
   uid,owner=await signup('writer');aid,admin=await signup('admin');rid,reader=await signup('reader')
   async with database.AsyncSessionLocal() as db:
    a=await db.get(User,aid);a.is_admin=True;u=await db.get(User,uid);u.credits_balance=10000;await db.commit()
   async def request(method,path,body=None,headers=owner,expect=200):
    response=await client.request(method,'/api/v1'+path,json=body,headers=headers)
    self.assertEqual(response.status_code,expect,response.text)
    return response.json()
   await request('POST','/books',{'title':'不应创建的旧自动流程','genre':'玄幻','generate_outline':True},expect=400)
   book=await request('POST','/books',{'title':'隔离测试小说','genre':'玄幻','generate_outline':False,'generate_characters':False,'generate_plots':False})
   bid=book['id'];chapter=await request('POST',f'/chapters/books/{bid}',{'title':'窑口'});cid=chapter['id']
   first=await request('PUT',f'/chapters/{cid}',{'content':'第一稿。','expected_hash':chapter['content_hash']})
   second=await request('PUT',f'/chapters/{cid}',{'content':'第二稿。','expected_hash':first['content_hash']})
   await request('PUT',f'/chapters/{cid}',{'content':'过期覆盖。','expected_hash':first['content_hash']},expect=409)
   revisions=await request('GET',f'/chapters/{cid}/revisions')
   old=next(r for r in revisions if r['word_count']>0)
   await request('GET',f'/chapters/{cid}/revisions/{old["id"]}',headers=reader,expect=404)
   restored=await request('POST',f'/chapters/{cid}/revisions/{old["id"]}/restore',{'expected_hash':second['content_hash']})
   self.assertEqual(restored['content'],'第一稿。')
   await request('GET',f'/community/books/{bid}/read',headers={},expect=404)
   await request('GET',f'/community/books/{bid}/read',headers=reader,expect=404)
   await request('GET',f'/community/books/{bid}/read')
   await request('POST',f'/books/{bid}/publication',headers=reader,expect=404)
   await request('POST',f'/books/{bid}/publication')
   public=await request('GET',f'/community/books/{bid}/read/chapters/{cid}',headers={})
   self.assertIn('第一稿',public['content'])
   await request('PUT',f'/chapters/{cid}',{'content':'尚未发布的新草稿。'})
   public=await request('GET',f'/community/books/{bid}/read/chapters/{cid}',headers={})
   self.assertNotIn('尚未发布',public['content'])
   await request('POST',f'/books/{bid}/publication/unpublish')
   await request('GET',f'/community/books/{bid}/read',headers={},expect=404)
   search=await request('GET','/community/search?q=隔离测试小说',headers=reader)
   self.assertFalse(any(b['id']==bid for b in search['books']))
   # Draft outlines must be explicitly confirmed; queued outline jobs survive clients.
   await request('POST','/jobs',{'book_id':bid,'chapter_id':cid,'kind':'generate','request_id':str(uuid4())},expect=409)
   await request('POST',f'/chapters/{cid}/generate',{},expect=409)
   plan={'volumes':[{'name':'第一卷','chapters':[{'number':1,'title':'窑口','summary':'小人物守护家人与家业。'}]}]}
   saved=await request('PUT',f'/books/{bid}/outline',{'content':plan})
   await request('POST',f'/books/{bid}/outline/confirm',{'content':plan},headers=reader,expect=404)
   await request('POST',f'/books/{bid}/outline/confirm',{'content':{'volumes':[]}},expect=409)
   confirmed=await request('POST',f'/books/{bid}/outline/confirm',{'content':plan})
   self.assertIn('_review',confirmed['content'])
   # Saving a new draft cannot smuggle a stale approval through the editable JSON.
   saved=await request('PUT',f'/books/{bid}/outline',{'content':confirmed['content']})
   self.assertNotIn('_review',saved['content'])
   outline_body={'book_id':bid,'kind':'outline','request_id':str(uuid4())}
   outline_job=await request('POST','/jobs',outline_body)
   self.assertEqual(outline_job['id'],(await request('POST','/jobs',outline_body))['id'])
   await request('POST','/jobs',{**outline_body,'request_id':str(uuid4())},expect=409)
   await request('POST','/jobs',{'book_id':bid,'kind':'analysis','request_id':str(uuid4())},expect=409)
   await request('PUT',f'/books/{bid}/outline',{'content':plan},expect=409)
   await request('POST',f'/books/{bid}/outline/confirm',{'content':plan},expect=409)
   from app.services.jobs import run_job
   with patch('app.api.outlines._call_langgraph',AsyncMock(return_value=(plan,None))) as outline_model:
    await run_job(outline_job['id'])
    outline_model.assert_awaited_once()
   self.assertEqual((await request('GET','/jobs/'+outline_job['id']))['status'],'succeeded')
   result=await request('GET',f'/books/{bid}/outline')
   self.assertNotIn('_review',result['content'])
   await request('POST',f'/books/{bid}/outline/confirm',{'content':result['content']})
   # Design drafts live in tasks until author adoption; same-name canon is preserved.
   await request('POST',f'/books/{bid}/config/world',{'name':'力量代价','category':'规则','description':'手工设定不可覆盖'})
   design_body={'book_id':bid,'kind':'story-design','design_type':'world','request_id':str(uuid4())}
   design_job=await request('POST','/jobs',design_body)
   model_design=AsyncMock(return_value=('共识',1,1,'platform-test'))
   model_design.return_value=('{'+'"summary":"世界观设计草案，等待作者核对。","dossiers":[{"name":"力量代价","category":"规则","description":"模型不能覆盖已经确认的手工力量代价规则。"},{"name":"窑城制度","category":"社会","description":"窑工按工分分享窑场收益，家族契约影响资源分配。"}]}',1,1,'platform-test')
   with patch('storyclaw.design.llm_respond',model_design),patch('app.services.creative_jobs.compute_cost',return_value=1):
    await run_job(design_job['id'])
   self.assertEqual((await request('GET',f'/books/{bid}/config/world'))['total'],1)
   await request('POST',f'/jobs/{design_job["id"]}/adopt',headers=reader,expect=404)
   adopted=await request('POST',f'/jobs/{design_job["id"]}/adopt')
   self.assertEqual((adopted['added'],adopted['skipped']),(1,1))
   await request('POST',f'/jobs/{design_job["id"]}/adopt')
   cards=(await request('GET',f'/books/{bid}/config/world'))['items']
   self.assertEqual(len(cards),2)
   self.assertEqual(next(r for r in cards if r['name']=='力量代价')['description'],'手工设定不可覆盖')
   # AI changes are versioned and charged in the same transaction, without a paid model.
   agent=AsyncMock(return_value={'draft_content':'来自模型的新稿。','token_usage':{'model_id':'platform-test','in_tokens':1,'out_tokens':1}})
   with patch('app.api.chat.run_agent',agent),patch('app.api.chat._build_input',AsyncMock(return_value={})),patch('app.services.setting_sync.launch'):
    await request('POST',f'/chapters/{cid}/generate',{})
   self.assertTrue(any(r['source']=='ai' for r in await request('GET',f'/chapters/{cid}/revisions')))
   before=(await request('GET',f'/chapters/{cid}'))['content']
   from fastapi import HTTPException
   with patch('app.api.chat.run_agent',agent),patch('app.api.chat._build_input',AsyncMock(return_value={})),patch('app.api.chat.debit',AsyncMock(side_effect=HTTPException(402,'积分不足'))):
    await request('POST',f'/chapters/{cid}/generate',{},expect=402)
   self.assertEqual((await request('GET',f'/chapters/{cid}'))['content'],before)
   with patch('app.api.writing.run_agent',agent),patch('app.api.writing.build_write_context',AsyncMock(return_value={})),patch('app.api.writing.debit',AsyncMock(side_effect=HTTPException(402,'积分不足'))):
    batch=await request('POST',f'/books/{bid}/multi-write',{'start_number':1,'end_number':1,'skip_existing':False,'sync_settings':False})
   self.assertEqual(batch['chapters'][0]['status'],'error')
   self.assertEqual(batch['total_credits_cost'],0)
   self.assertEqual((await request('GET',f'/chapters/{cid}'))['content'],before)
   # A browser edit during a slow generation must win over the late model result.
   import asyncio
   entered=asyncio.Event();release=asyncio.Event()
   async def slow_agent(*args):
    entered.set();await release.wait();return {'draft_content':'迟到的生成稿','token_usage':{}}
   with patch('app.api.chat.run_agent',slow_agent),patch('app.api.chat._build_input',AsyncMock(return_value={})),patch('app.services.setting_sync.launch'):
    late=asyncio.create_task(client.post(f'/api/v1/chapters/{cid}/generate',headers=owner,json={}))
    await asyncio.wait_for(entered.wait(),5)
    await request('PUT',f'/chapters/{cid}',{'content':'并发编辑的新正文。'})
    release.set();response=await late
    self.assertEqual(response.status_code,409,response.text)
   self.assertEqual((await request('GET',f'/chapters/{cid}'))['content'],'并发编辑的新正文。')
   body={'book_id':bid,'chapter_id':cid,'kind':'scene-plan','request_id':str(uuid4())}
   job=await request('POST','/jobs',body);again=await request('POST','/jobs',body);self.assertEqual(job['id'],again['id'])
   await request('GET','/jobs/'+job['id'],headers=reader,expect=404)
   await request('PUT',f'/chapters/{cid}',{'content':'不能覆盖任务中的章节'},expect=409)
   await request('POST','/jobs/'+job['id']+'/cancel')
   body['request_id']=str(uuid4());body['kind']='index'
   body['reviewed_hash']=(await request('GET',f'/chapters/{cid}'))['content_hash']
   job=await request('POST','/jobs',body)
   async with database.AsyncSessionLocal() as db:
    j=await db.get(WorkJob,job['id']);j.status='running';await db.commit()
   from app.schemas import IngestOut
   from app.services.jobs import run_job
   with patch('app.api.rag.ingest_chapter_endpoint',AsyncMock(return_value=IngestOut(chapter_id=cid,chunks=3,entities=2,relations=1,rag_status='loaded',error=None))):await run_job(job['id'])
   self.assertEqual((await request('GET','/jobs/'+job['id']))['status'],'succeeded')
   # A failed worker records a terminal error rather than leaving a spinner forever.
   import asyncio
   from app.services.jobs import queue_loop
   body['request_id']=str(uuid4())
   failed_job=await request('POST','/jobs',body)
   with patch('app.services.jobs.run_job',AsyncMock(side_effect=HTTPException(502,'测试供应商失败'))):
    task=asyncio.create_task(queue_loop())
    try:
     for _ in range(40):
      await asyncio.sleep(.05)
      status=await request('GET','/jobs/'+failed_job['id'])
      if status['status']=='failed':break
     self.assertEqual(status['status'],'failed');self.assertIn('测试供应商失败',status['error'])
    finally:
     task.cancel()
     try:await task
     except asyncio.CancelledError:pass
   # Moderated community interactions are idempotent and HTML is sanitized.
   # Current manuscript approval is required to index; next chapter waits for memory.
   next_chapter=await request('POST',f'/chapters/books/{bid}',{'title':'出城'})
   next_body={'book_id':bid,'chapter_id':next_chapter['id'],'kind':'generate','request_id':str(uuid4())}
   await request('POST','/jobs',next_body,expect=409)
   await request('POST','/jobs',{'book_id':bid,'chapter_id':cid,'kind':'index','request_id':str(uuid4())},expect=409)
   current=await request('GET',f'/chapters/{cid}')
   index_job=await request('POST','/jobs',{'book_id':bid,'chapter_id':cid,'kind':'index','request_id':str(uuid4()),'reviewed_hash':current['content_hash']})
   with patch('app.api.rag.rag_svc.ingest_text',AsyncMock(return_value={'chunks':2,'entities':1,'relations':0,'stores':{'vector':'milvus','graph':'neo4j'},'error':None})):
    await run_job(index_job['id'])
   self.assertEqual((await request('GET',f'/chapters/{cid}'))['rag_status'],'loaded')
   next_job=await request('POST','/jobs',{**next_body,'request_id':str(uuid4())})
   await request('POST',f'/jobs/{next_job["id"]}/cancel')
   await request('PUT',f'/chapters/{cid}',{'content':'上章修订使旧索引失效。'})
   await request('POST','/jobs',{**next_body,'request_id':str(uuid4())},expect=409)
   post=await request('POST','/community/posts',{'title':'写作讨论','content_html':'<p onclick="evil()">正文</p><img src=x onerror=evil()><a href="javascript:evil()">链接</a>','content_text':'正文'})
   pid=post['id'];self.assertNotIn('onclick',post['content_html']);self.assertNotIn('javascript',post['content_html']);self.assertNotIn('<img',post['content_html'])
   for _ in range(2):await request('PUT',f'/community/posts/{pid}/like',{'liked':True},headers=reader)
   self.assertEqual((await request('GET',f'/community/posts/{pid}/engagement'))['likes'],1)
   comment=await request('POST',f'/community/posts/{pid}/comments',{'content':'很喜欢这个设定'},headers=reader)
   await request('DELETE',f'/community/comments/{comment["id"]}',expect=404)
   await request('DELETE',f'/community/comments/{comment["id"]}',headers=reader)
   for _ in range(2):await request('POST',f'/community/posts/{pid}/report',{'reason':'请运营核实内容'},headers=reader)
   await request('GET','/operations/reports',headers=reader,expect=403)
   reports=await request('GET','/operations/reports',headers=admin);r=next(r for r in reports if r['post_id']==pid)
   await request('POST',f'/operations/reports/{r["id"]}/review',{'action':'hide','note':'测试下架流程'},headers=admin)
   await request('GET',f'/community/posts/{pid}',headers=reader,expect=404)
   await request('POST',f'/operations/reports/{r["id"]}/review',{'action':'restore','note':'核实后恢复展示'},headers=admin)
   await request('GET',f'/community/posts/{pid}',headers=reader)
   # Manual membership activation is atomic and repeat approval grants only once.
   await request('PUT','/admin/membership',{'memberships':[{'id':'test-month','name':'测试会员','price_cny':30,'duration_days':30,'bonus_credits':20,'enabled':True}]},headers=admin)
   order_data={'membership_id':'test-month','request_id':str(uuid4())}
   order=await request('POST','/wallet/orders',order_data)
   self.assertEqual(order['id'],(await request('POST','/wallet/orders',order_data))['id'])
   await request('POST',f'/operations/orders/{order["id"]}/review',{'action':'approve','note':'越权不应通过'},headers=reader,expect=403)
   balance=(await request('GET','/wallet'))['credits_balance']
   for _ in range(2):await request('POST',f'/operations/orders/{order["id"]}/review',{'action':'approve','note':'测试人工开通'},headers=admin)
   wallet=await request('GET','/wallet');self.assertEqual(wallet['credits_balance'],balance+20);self.assertTrue(wallet['membership']['active'])
   await request('POST',f'/operations/orders/{order["id"]}/review',{'action':'reject','note':'已通过不可拒绝'},headers=admin,expect=409)
   self.assertTrue((await request('GET','/wallet/ledger'))['total']>0)
  await database.engine.dispose()
