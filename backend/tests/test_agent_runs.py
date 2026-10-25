import os,unittest
from uuid import uuid4
from unittest.mock import patch,AsyncMock
import httpx
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from storyclaw.contracts import ModelTurn,ToolCall

class AgentRunsTests(unittest.IsolatedAsyncioTestCase):
 async def test_scoped_commands_chat_decisions_and_replay(self):
  url=os.environ.get('DATABASE_URL','')
  if not url.endswith('/storyclaw_refactor_test'):self.skipTest('isolated database required')
  import app.database as database
  await database.engine.dispose();database.engine=create_async_engine(url,poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base,User
  from app.models.agent import AgentRun
  from app.services.agent_runs import poll_once
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
   book=await call('POST','/books',{'title':'Agent集成测试','intro':'私密的测试资料'})
   bid=book['id'];chapter=await call('POST',f'/chapters/books/{bid}',{'title':'第一章'})
   await call('PUT',f'/chapters/{chapter["id"]}',{'content':'夜雨落在窗前，灯匠收好了铜钳。'})
   # Commands are synchronous deterministic enqueue, and use the legacy queue/policies.
   body={'request_id':str(uuid4()),'entry':'command','command':'framework.draft','scope':{'book_id':bid},'payload':{'planning_mode':'serial'}}
   first=await call('POST','/agent/runs',body)
   self.assertEqual(first['status'],'waiting_task');self.assertTrue(first['job_id'])
   again=await call('POST','/agent/runs',body);self.assertEqual(first['id'],again['id'])
   await call('POST','/agent/runs',{**body,'payload':{'planning_mode':'fixed'}},409)
   await call('GET',f'/agent/runs/{first["id"]}',status=404,headers=other)
   await call('POST','/agent/runs',{**body,'request_id':str(uuid4())},404,headers=other)
   events=await call('GET',f'/agent/runs/{first["id"]}/events')
   self.assertEqual([e['seq'] for e in events],list(range(1,len(events)+1)))
   replay=await call('GET',f'/agent/runs/{first["id"]}/events?after_seq={events[-1]["seq"]}')
   self.assertEqual(replay,[])
   await call('POST',f'/agent/runs/{first["id"]}/cancel')
   # Chat cannot fabricate author approval for indexing existing text.
   request={'request_id':str(uuid4()),'entry':'chat','message':'把本章加入记忆',
       'scope':{'book_id':bid,'chapter_id':chapter['id']}}
   run=await call('POST','/agent/runs',request)
   detail=await call('GET',f'/chapters/{chapter["id"]}')
   model=AsyncMock(return_value=ModelTurn(calls=[ToolCall(name='knowledge__ingest',arguments={'reviewed_hash':detail['content_hash']})]))
   with patch('app.services.story_ports.agent.BackendStoryPorts.model_turn',model):await poll_once()
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
   with patch('app.services.story_ports.agent.BackendStoryPorts.model_turn',model):
    self.assertFalse(await poll_once())
