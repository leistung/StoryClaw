import os,unittest
from uuid import uuid4
from unittest.mock import patch,AsyncMock
import httpx
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from storyclaw.contracts import ModelTurn
from storyclaw.contracts import ToolCall

class AgentRunsTests(unittest.IsolatedAsyncioTestCase):
 async def test_scoped_commands_chat_decisions_and_replay(self):
  url=os.environ.get('DATABASE_URL','')
  if not url.endswith('/storyclaw_refactor_test'):self.skipTest('isolated database required')
  import app.database as database
  await database.engine.dispose();database.engine=create_async_engine(url,poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base
  from app.models import User
  from app.models.agent import AgentRun
  from app.services.agent.agent_runs import poll_once
  async with database.engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
   async def account():
    name='agent'+uuid4().hex[:10]
    await client.post('/api/v1/auth/register',json={'username':name,'password':'test123456'})
    r=(await client.post('/api/v1/auth/login',json={'username':name,'password':'test123456'})).json()
    return {'Authorization':'Bearer '+r['token']},r['user']['id']
   h,uid=await account();other,_=await account()
   async with database.AsyncSessionLocal() as db:
    user=await db.get(User,uid);user.credits_balance=10000;await db.commit()
   async def call(method,path,data=None,status=200,headers=None):
    r=await client.request(method,'/api/v1'+path,json=data,headers=headers or h)
    self.assertEqual(r.status_code,status,r.text);return r.json()
   book=await call('POST','/books',{'title':'Agent集成测试','genre':'玄幻','intro':'私密的测试资料'})
   bid=book['id'];chapter=await call('POST',f'/chapters/books/{bid}',{'title':'第一章'})
   await call('PUT',f'/chapters/{chapter["id"]}',{'content':'夜雨落在窗前，灯匠收好了铜钳。'})
   # Planning commands draft a reviewable plan; no paid generation job before approval.
   body={'request_id':str(uuid4()),'entry':'command','command':'framework.draft','scope':{'book_id':bid},'payload':{'planning_mode':'serial'}}
   first=await call('POST','/agent/runs',body)
   self.assertEqual(first['status'],'accepted');self.assertIsNone(first['job_id'])
   again=await call('POST','/agent/runs',body);self.assertEqual(first['id'],again['id'])
   await call('POST','/agent/runs',{**body,'payload':{'planning_mode':'fixed'}},409)
   await call('GET',f'/agent/runs/{first["id"]}',status=404,headers=other)
   await call('POST','/agent/runs',{**body,'request_id':str(uuid4())},404,headers=other)
   from storyclaw.workflows.creation_plan import CreationPlan
   plan=CreationPlan(goal='围绕失踪案、河灯规则和父子关系设计完整分卷，每卷推进不同冲突。',
       sections=[{'name':'雾港来灯','brief':'河灯匠接到父亲留下的破灯，发现旧码头被隐瞒的航线，与商会发生冲突。'}],item_count=1,detail_words=600)
   with patch('storyclaw.workflows.creation_plan.propose_plan',AsyncMock(return_value=plan)):
    await poll_once()
   first=await call('GET',f'/agent/runs/{first["id"]}')
   self.assertEqual(first['status'],'waiting_author');self.assertIsNone(first['job_id'])
   old_decision=first['decision']['id']
   revision={'decision_id':old_decision,'feedback':'增加商会竞争线，保持一卷但展开到800字'}
   await call('POST',f'/agent/runs/{first["id"]}/plan',revision,404,headers=other)
   await call('POST',f'/agent/runs/{first["id"]}/plan',revision)
   plan.detail_words=800
   with patch('storyclaw.workflows.creation_plan.propose_plan',AsyncMock(return_value=plan)) as propose:
    await poll_once()
    self.assertIn('商会竞争线',propose.call_args.args[1]['feedback'])
   first=await call('GET',f'/agent/runs/{first["id"]}')
   self.assertNotEqual(first['decision']['id'],old_decision)
   await call('POST',f'/agent/runs/{first["id"]}/decisions',{'decision_id':old_decision,'accept':True},409)
   # Changed project inputs invalidate the plan until it is regenerated.
   from app.models import Book
   async with database.AsyncSessionLocal() as db:
    b=await db.get(Book,bid);b.intro='新的商战方向与旧港秘密';await db.commit()
   choice={'decision_id':first['decision']['id'],'accept':True}
   await call('POST',f'/agent/runs/{first["id"]}/decisions',choice,409)
   await call('POST',f'/agent/runs/{first["id"]}/plan',{'decision_id':choice['decision_id'],'feedback':'按更新的商战方向重新拟订'})
   with patch('storyclaw.workflows.creation_plan.propose_plan',AsyncMock(return_value=plan)):await poll_once()
   first=await call('GET',f'/agent/runs/{first["id"]}')
   first=await call('POST',f'/agent/runs/{first["id"]}/decisions',{'decision_id':first['decision']['id'],'accept':True})
   self.assertEqual(first['status'],'waiting_task');self.assertTrue(first['job_id'])
   from app.models.product import WorkJob
   async with database.AsyncSessionLocal() as db:
    job=await db.get(WorkJob,first['job_id']);self.assertEqual(job.payload['creation_plan']['detail_words'],800)
   from app.services.agent.job_progress import emit
   await emit(first['job_id'],'tool.started',{'name':'query_memory','arguments':{'query':'商会'}})
   await emit(first['job_id'],'tool.failed',{'name':'query_memory','error':'检索服务不可用'})
   events=await call('GET',f'/agent/runs/{first["id"]}/events')
   self.assertEqual([e['seq'] for e in events],list(range(1,len(events)+1)))
   self.assertTrue(any(e['type']=='tool.failed' and e['payload'].get('error')=='检索服务不可用' for e in events))
   replay=await call('GET',f'/agent/runs/{first["id"]}/events?after_seq={events[-1]["seq"]}')
   self.assertEqual(replay,[])
   await call('POST',f'/agent/runs/{first["id"]}/cancel')
   # Chat cannot fabricate author approval for indexing existing text.
   request={'request_id':str(uuid4()),'entry':'chat','message':'把本章加入记忆',
       'scope':{'book_id':bid,'chapter_id':chapter['id']}}
   run=await call('POST','/agent/runs',request)
   detail=await call('GET',f'/chapters/{chapter["id"]}')
   model=AsyncMock(return_value=ModelTurn(calls=[ToolCall(name='knowledge__ingest',arguments={'reviewed_hash':detail['content_hash']})]))
   with patch('app.adapters.storyclaw.agent.BackendStoryPorts.model_turn',model):await poll_once()
   run=await call('GET',f'/agent/runs/{run["id"]}')
   self.assertEqual(run['status'],'waiting_author');self.assertFalse(run['job_id'])
   decision={'decision_id':run['decision']['id'],'accept':True}
   await call('POST',f'/agent/runs/{run["id"]}/decisions',decision,404,headers=other)
   # An edited body invalidates the exact approval card.
   await call('PUT',f'/chapters/{chapter["id"]}',{'content':'灯匠收好铜钳后，发现了新的暗号。'})
   await call('POST',f'/agent/runs/{run["id"]}/decisions',decision,409)
   await call('POST',f'/agent/runs/{run["id"]}/decisions',{**decision,'accept':False})
   # A cancelled run is never picked back up by the queue.
   pending=await call('POST','/agent/runs',{**request,'request_id':str(uuid4())})
   await call('POST',f'/agent/runs/{pending["id"]}/cancel')
   with patch('app.adapters.storyclaw.agent.BackendStoryPorts.model_turn',model):
    self.assertFalse(await poll_once())

   # A cancelled, crashed run cannot retain a reservation forever or refund it twice.
   from datetime import datetime,timedelta,timezone
   async with database.AsyncSessionLocal() as db:
    row=await db.get(AgentRun,pending['id']);row.reserved=7;row.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)
    user=await db.get(User,uid);before=user.credits_balance;user.credits_balance-=7;await db.commit()
   await poll_once();await poll_once()
   async with database.AsyncSessionLocal() as db:
    self.assertEqual((await db.get(User,uid)).credits_balance,before)
    self.assertEqual((await db.get(AgentRun,pending['id'])).status,'cancelled')
