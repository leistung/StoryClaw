import os,json,unittest
from uuid import uuid4
from unittest.mock import AsyncMock,patch
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
class GuidedIntegration(unittest.IsolatedAsyncioTestCase):
 async def test_persistent_two_round_flow_revision_and_ownership(self):
  url=os.environ.get('DATABASE_URL','')
  if not url.endswith('/storyclaw_refactor_test'):self.skipTest('isolated database required')
  import app.database as database
  await database.engine.dispose();database.engine=create_async_engine(url,poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base
  from app.models import User
  from app.models.ideation import IdeationSession
  async with database.engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
   async def signup():
    name='guided'+uuid4().hex[:8]
    await client.post('/api/v1/auth/register',json={'username':name,'password':'test123456'})
    data=(await client.post('/api/v1/auth/login',json={'username':name,'password':'test123456'})).json()
    return data['user']['id'],{'Authorization':'Bearer '+data['token']}
   uid,owner=await signup();_,other=await signup()
   async with database.AsyncSessionLocal() as db:u=await db.get(User,uid);u.credits_balance=100;await db.commit()
   async def ask(content,session=None,answers=None,mode='discuss',request_id=None,headers=owner):
    return await client.post('/api/v1/assist/ideation',headers=headers,json={'guided':True,'request_id':request_id or str(uuid4()),'mode':mode,'session_id':session,'messages':[{'role':'user','content':content}],'answers':answers or []})
   draft={'reply':'以下是方案，请采用或提出修改。','proposal':{'title':'灯火小城','intro':'一名普通人在架空历史的乱世里经营小店，保护家人，通过团结邻里改变命运。','genre':'历史','protagonist_name':'沈砚','protagonist_intro':'市井经营者，善良而坚韧，希望守住家人与家乡。','target_chapters':40,'per_chapter_words':2500}}
   mock=AsyncMock(return_value=(json.dumps(draft),20,30,'test-model'))
   with patch('storyclaw.workflows.ideation.engine.llm_respond',mock),patch('app.gateway.routers.ideation.compute_cost',return_value=1),patch('app.gateway.routers.ideation.refresh_configs',AsyncMock()):
    first=(await ask('我想写小说，请帮助我确定方向')).json();session=first['session_id']
    self.assertEqual(first['question_round'],1);self.assertEqual(first['credits_cost'],0);self.assertEqual(mock.await_count,0)
    second=(await ask('选择历史',session,[{'id':'genre','values':['历史']},{'id':'tone','values':['温暖治愈']},{'id':'length','values':['长篇起步（约10万字）']}])).json()
    self.assertEqual(second['question_round'],2);self.assertIn('架空历史',second['questions'][0]['options']);self.assertEqual(mock.await_count,0)
    denied=await ask('读取会话',session,headers=other);self.assertEqual(denied.status_code,404)
    key=str(uuid4());answers=[{'id':'subgenre','values':['架空历史']},{'id':'protagonist','values':['经营者']},{'id':'conflict','values':['种田经营']}]
    response=await ask('已确认',session,answers,request_id=key);self.assertEqual(response.status_code,200,response.text)
    result=response.json();self.assertEqual(result['stage'],'review');self.assertEqual(result['question_round'],2);self.assertFalse(result['questions']);self.assertIsNotNone(result['proposal'])
    replay=await ask('已确认',session,answers,request_id=key);self.assertEqual(replay.json(),result);self.assertEqual(mock.await_count,1)
    revised=(await ask('只修改书名，其他保持不变',session,mode='revise')).json();self.assertFalse(revised['questions']);self.assertEqual(revised['question_round'],2);self.assertEqual(mock.await_count,2)
    self.assertIn('架空历史',mock.call_args.args[2]);self.assertIn('温暖治愈',mock.call_args.args[2])
    async with database.AsyncSessionLocal() as db:
     self.assertEqual((await db.get(User,uid)).credits_balance,98)
     self.assertEqual((await db.get(IdeationSession,session)).state['round'],2)
