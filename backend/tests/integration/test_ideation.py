import os,json,unittest
from uuid import uuid4
from unittest.mock import AsyncMock,patch
import httpx
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

class IdeationIntegration(unittest.IsolatedAsyncioTestCase):
 async def test_confirmed_proposal_idempotency_and_validation(self):
  url=os.environ.get('DATABASE_URL','')
  if not url.endswith('/storyclaw_refactor_test'):self.skipTest('Requires isolated test database')
  import app.database as database
  await database.engine.dispose();database.engine=create_async_engine(url,poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base
  from app.models import User
  from app.models import Book
  from app.models import CreditsLedger
  async with database.engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
   username='idea'+uuid4().hex[:10]
   await c.post('/api/v1/auth/register',json={'username':username,'password':'test123456'})
   login=(await c.post('/api/v1/auth/login',json={'username':username,'password':'test123456'})).json();uid=login['user']['id'];headers={'Authorization':'Bearer '+login['token']}
   async with database.AsyncSessionLocal() as db:
    u=await db.get(User,uid);u.credits_balance=100;await db.commit()
   body={'request_id':str(uuid4()),'genre':'玄幻','mode':'proposal','messages':[{'role':'user','content':'写一个窑工的成长故事'}]}
   draft={'reply':'建议从普通人的选择展开，请确认。','proposal':{'title':'窑火长明','intro':'一个年轻窑工发现祖辈的契约秘密，决定通过自己的劳动和调查改变家族的命运。','genre':'玄幻','protagonist_name':'许生','protagonist_intro':'一名倔强而诚实的年轻窑工，想守住家人与祖窑。','target_chapters':40,'per_chapter_words':2500}}
   mock=AsyncMock(return_value=(json.dumps(draft,ensure_ascii=False),100,200,'test-model'))
   with patch('storyclaw.workflows.ideation.engine.llm_respond',mock),patch('app.gateway.routers.ideation.compute_cost',return_value=7),patch('app.gateway.routers.ideation.refresh_configs',AsyncMock()):
    first=await c.post('/api/v1/assist/ideation',headers=headers,json=body);self.assertEqual(first.status_code,200,first.text)
    self.assertEqual(first.json()['proposal']['title'],'窑火长明')
    second=await c.post('/api/v1/assist/ideation',headers=headers,json=body);self.assertEqual(second.json(),first.json());self.assertEqual(mock.await_count,1)
    altered={**body,'genre':'科幻'};self.assertEqual((await c.post('/api/v1/assist/ideation',headers=headers,json=altered)).status_code,409)
    async with database.AsyncSessionLocal() as db:
     self.assertEqual((await db.get(User,uid)).credits_balance,93)
     self.assertEqual(await db.scalar(select(func.count()).select_from(Book).where(Book.user_id==uid)),0)
     self.assertEqual(await db.scalar(select(func.count()).select_from(CreditsLedger).where(CreditsLedger.user_id==uid,CreditsLedger.reason=='ideation')),1)
    mock.return_value=('{}',1,1,'test-model')
    bad=await c.post('/api/v1/assist/ideation',headers=headers,json={**body,'request_id':str(uuid4())});self.assertEqual(bad.status_code,502)
    async with database.AsyncSessionLocal() as db:
     self.assertEqual((await db.get(User,uid)).credits_balance,93)
    mock.return_value=(json.dumps(draft),1,1,'test-model')
    discussion=await c.post('/api/v1/assist/ideation',headers=headers,json={**body,'request_id':str(uuid4()),'mode':'discuss'});self.assertIsNone(discussion.json()['proposal'])
   async def streamed(state,system,prompt,on_delta):
    raw=json.dumps(draft,ensure_ascii=False)
    for offset in range(0,len(raw),7):await on_delta(raw[offset:offset+7])
    return raw,100,200,'test-model'
   with patch('storyclaw.workflows.ideation.engine.stream_llm_respond',AsyncMock(side_effect=streamed)) as stream_mock,patch('app.gateway.routers.ideation.compute_cost',return_value=7),patch('app.gateway.routers.ideation.refresh_configs',AsyncMock()):
    payload={**body,'request_id':str(uuid4())}
    response=await c.post('/api/v1/assist/ideation/stream',headers=headers,json=payload)
    self.assertEqual(response.status_code,200,response.text)
    self.assertIn('event: delta',response.text);self.assertIn('event: done',response.text)
    self.assertLess(response.text.index('event: delta'),response.text.index('event: done'))
    replay=await c.post('/api/v1/assist/ideation/stream',headers=headers,json=payload)
    self.assertIn('event: done',replay.text);self.assertEqual(stream_mock.await_count,1)
   self.assertIn((await c.post('/api/v1/assist/ideation',json=body)).status_code,[401,403])
   self.assertEqual((await c.post('/api/v1/assist/ideation',headers=headers,json={**body,'messages':[{'role':'system','content':'invalid'}]})).status_code,422)
