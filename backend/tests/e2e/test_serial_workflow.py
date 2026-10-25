import os,unittest
from uuid import uuid4
from unittest.mock import patch,AsyncMock
import httpx
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from storyclaw.workflows.serial import Blueprint

class SerialWorkflowTests(unittest.IsolatedAsyncioTestCase):
 async def test_rolling_plans_indexing_and_retroactive_changes(self):
  url=os.environ.get('DATABASE_URL','')
  if not url.endswith('/storyclaw_refactor_test'):self.skipTest('isolated DB required')
  import app.database as database
  await database.engine.dispose();database.engine=create_async_engine(url,poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base
  from app.models import User
  from app.services.jobs.jobs import run_job
  async with database.engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
   name='serial'+uuid4().hex[:8]
   await client.post('/api/v1/auth/register',json={'username':name,'password':'test123456'})
   auth=(await client.post('/api/v1/auth/login',json={'username':name,'password':'test123456'})).json()
   headers={'Authorization':'Bearer '+auth['token']}
   async with database.AsyncSessionLocal() as db:
    u=await db.get(User,auth['user']['id']);u.credits_balance=10000;await db.commit()
   async def req(method,path,data=None,status=200):
    response=await client.request(method,'/api/v1'+path,json=data,headers=headers)
    self.assertEqual(response.status_code,status,response.text);return response.json()
   b=await req('POST','/books',{'title':'连载流程测试','genre':'玄幻','intro':'河灯匠寻找失踪的父亲，逐步发现雾港的旧约。','target_chapters':12})
   bid=b['id'];frame={'planning_mode':'serial','overview':'一个河灯匠在雾港修灯追查失踪案，守住家人和灯火，结局保持开放。','volumes':[{'name':'寻灯','goal':'找到失灯线索并理解规则代价，随后视实际剧情继续扩展。','chapters':[]}]}
   await req('PUT',f'/books/{bid}/outline',{'content':frame});await req('POST',f'/books/{bid}/outline/confirm',{'content':frame})
   c1=await req('POST',f'/chapters/books/{bid}',{'title':'河灯'});c2=await req('POST',f'/chapters/books/{bid}',{'title':'潮痕'})
   async def enqueue(cid,kind,**extra):return await req('POST','/jobs',{'book_id':bid,'chapter_id':cid,'kind':kind,'request_id':str(uuid4()),**extra})
   await req('POST','/jobs',{'book_id':bid,'chapter_id':c1['id'],'kind':'generate','request_id':str(uuid4())},status=409)
   plan={'title':'夜修河灯','summary':'河灯匠在暴雨中接到一盏破灯，发现灯罩刻着父亲留下的暗号，决定次日去旧码头寻找线索。','ending_hook':'灯芯照出一条潮线','constraints':['父亲失踪而非死亡']}
   await req('PUT',f'/chapters/{c1["id"]}/blueprint',plan)
   await req('POST',f'/chapters/{c1["id"]}/blueprint/confirm',plan)
   agent=AsyncMock(return_value={'draft_content':'河灯匠修好了灯，在灯芯里发现了父亲留下的潮线记号。','token_usage':{}})
   with patch('app.services.writing.chat_workflow.chapters.run_agent',agent),patch('app.services.platform.pricing.compute_cost',return_value=1):
    job=await enqueue(c1['id'],'generate');await run_job(job['id'])
   await req('POST','/jobs',{'book_id':bid,'chapter_id':c2['id'],'kind':'chapter-outline','request_id':str(uuid4())},status=409)
   async def index(cid):
    detail=await req('GET',f'/chapters/{cid}')
    job=await enqueue(cid,'index',reviewed_hash=detail['content_hash'])
    with patch('app.services.knowledge.knowledge_workflow.rag_svc.ingest_text',AsyncMock(return_value={'chunks':2,'entities':1,'relations':1,'stores':{'vector':'milvus','graph':'neo4j'},'error':None})):
     await run_job(job['id'])
   await index(c1['id'])
   plan2=Blueprint(title='潮线入巷',summary='河灯匠循着父亲留下的潮线来到旧巷，询问守潮老人，发现旧码头的灯印与失踪案有关。',ending_hook='老人递来半枚灯印',constraints=['父亲仍然失踪'])
   with patch('app.services.platform.pricing.compute_cost',return_value=1),patch('app.services.writing.serial.generate_blueprint',AsyncMock(return_value=(plan2,1,1,'platform-test'))) as planner,patch('storyclaw.context.writing_context.query_context',AsyncMock(return_value={'chunks':[{'chapter_id':c1['id'],'text':'潮线记号'}],'relations':[]})):
    job=await enqueue(c2['id'],'chapter-outline');await run_job(job['id'])
    self.assertIn('潮线记号',planner.call_args.args[2]['prev_chapter_summary'])
   state=await req('GET',f'/chapters/{c2["id"]}/blueprint');self.assertFalse(state['confirmed'])
   await req('POST',f'/chapters/{c2["id"]}/blueprint/confirm',state['plan'])
   await req('PUT',f'/chapters/{c2["id"]}',{'content':'守潮老人递出半枚灯印，让河灯匠去找旧码头的船夫。'})
   await index(c2['id'])
   self.assertTrue((await req('GET',f'/chapters/{c2["id"]}/blueprint'))['confirmed'])
   # Changing chapter one invalidates chapter two's memory and blueprint, without rewriting it.
   original=(await req('GET',f'/chapters/{c2["id"]}'))['content']
   await req('PUT',f'/chapters/{c1["id"]}',{'content':'修灯时发现的线索改为一枚完整灯印，不再是潮线。'})
   second=await req('GET',f'/chapters/{c2["id"]}')
   self.assertEqual(second['content'],original);self.assertEqual(second['rag_status'],'pending')
   self.assertTrue((await req('GET',f'/chapters/{c2["id"]}/blueprint'))['stale'])
   self.assertTrue((await req('GET',f'/books/{bid}/workflow'))['impacts'])
   await index(c1['id']);await index(c2['id'])
   self.assertFalse((await req('GET',f'/books/{bid}/workflow'))['impacts'])
