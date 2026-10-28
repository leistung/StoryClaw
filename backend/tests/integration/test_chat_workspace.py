"""The chat owns execution; exact manuscript references survive detached UI state."""
import os,unittest
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import httpx
from sqlalchemy import select,func
from storyclaw.contracts import ModelTurn,ToolCall

class ChatWorkspaceTests(unittest.IsolatedAsyncioTestCase):
 async def test_references_candidates_and_studio_author_decisions(self):
  url=os.environ.get('DATABASE_URL','')
  if not url.endswith('/storyclaw_refactor_test'):self.skipTest('isolated database required')
  import app.database as database
  from sqlalchemy.ext.asyncio import create_async_engine
  from sqlalchemy.pool import NullPool
  await database.engine.dispose();database.engine=create_async_engine(url,poolclass=NullPool);database.AsyncSessionLocal.configure(bind=database.engine)
  from app.main import app
  from app.models import Base,User
  from app.models.studio import StudioTask
  from app.services.agent.agent_runs import execute_run
  async with database.engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
   name='chat'+uuid4().hex[:10]
   await client.post('/api/v1/auth/register',json={'username':name,'password':'test123456'})
   login=(await client.post('/api/v1/auth/login',json={'username':name,'password':'test123456'})).json()
   headers={'Authorization':'Bearer '+login['token']}
   async with database.AsyncSessionLocal() as db:
    user=await db.get(User,login['user']['id']);user.credits_balance=10000;await db.commit()
   async def call(method,path,data=None,status=200):
    response=await client.request(method,'/api/v1'+path,json=data,headers=headers)
    self.assertEqual(response.status_code,status,response.text);return response.json()
   book=await call('POST','/books',{'title':'单一对话入口测试','genre':'现实'})
   chapter=await call('POST',f'/chapters/books/{book["id"]}',{'title':'夜雨'})
   html='<p><strong>夜雨落下。</strong></p><p>夜雨落下。</p><p><em>后文保留。</em></p>'
   chapter=await call('PUT',f'/chapters/{chapter["id"]}',{'content':html})
   scope={'book_id':book['id'],'chapter_id':chapter['id']}
   ref={'kind':'selection','chapter_id':chapter['id'],'title':'夜雨','line_start':2,'line_end':2,
        'text':'夜雨落下。','offset':5,'expected_hash':chapter['content_hash']}
   async def request_run(message,references=None):
    return await call('POST','/agent/runs',{'request_id':str(uuid4()),'entry':'chat','message':message,'scope':scope,'references':references or []})
   run=await request_run('润色第二处选区，保留第一段。',[ref])
   self.assertEqual(run['status'],'accepted')
   result=SimpleNamespace(content='晨光初现。',credits_cost=0)
   turn=ModelTurn(calls=[ToolCall(name='text__polish',arguments={'instruction':'只改引用的选区'})])
   with patch('app.adapters.storyclaw.agent.BackendStoryPorts.model_turn',AsyncMock(return_value=turn)),patch('app.services.writing.writing_workflow.polish_chapter',AsyncMock(return_value=result)) as polish:
    await execute_run(run['id'])
    self.assertEqual(polish.call_args.args[1].selected_text,'夜雨落下。')
   run=await call('GET',f'/agent/runs/{run["id"]}')
   original_request=run['request']
   self.assertEqual(run['result']['data']['range'],{'start':5,'end':10,'text':'夜雨落下。'})
   await call('POST',f'/agent/runs/{run["id"]}/adopt',{'expected_hash':chapter['content_hash']})
   current=await call('GET',f'/chapters/{chapter["id"]}')
   self.assertEqual(current['content'],'<p><strong>夜雨落下。</strong></p><p>晨光初现。</p><p><em>后文保留。</em></p>')
   replay=await call('POST','/agent/runs',original_request)
   self.assertEqual(replay['id'],run['id'])
   await call('POST','/agent/runs',{'request_id':str(uuid4()),'message':'旧引用','scope':scope,'references':[ref]},409)
   other=await call('POST',f'/chapters/books/{book["id"]}',{'title':'另一章'})
   await call('POST','/agent/runs',{'request_id':str(uuid4()),'message':'错章引用','scope':{**scope,'chapter_id':other['id']},'references':[ref]},422)

   # Continuation respects the attached cursor, receives the whole prefix and author instruction.
   cursor={**ref,'kind':'cursor','offset':2,'text':'夜雨▏落下','expected_hash':current['content_hash'],'affinity':'after'}
   run=await request_run('请在光标处续写，保留光标之后的内容。',[cursor])
   result=SimpleNamespace(content='忽然停了，',credits_cost=0)
   with patch('app.adapters.storyclaw.agent.BackendStoryPorts.model_turn',AsyncMock(return_value=ModelTurn(calls=[ToolCall(name='text__continue',arguments={'instruction':'增加一次停顿'})]))),patch('app.services.writing.writing_workflow.continue_writing',AsyncMock(return_value=result)) as continuation:
    await execute_run(run['id'])
    data=continuation.call_args.args[1]
    self.assertEqual(data.cursor_offset,2);self.assertEqual(data.prefix_text,'夜雨');self.assertEqual(data.instruction,'增加一次停顿')
   await call('POST',f'/agent/runs/{run["id"]}/adopt',{'expected_hash':current['content_hash']})
   current=await call('GET',f'/chapters/{chapter["id"]}')
   self.assertIn('夜雨忽然停了，',current['content']);self.assertTrue(current['content'].endswith('<p><em>后文保留。</em></p>'))

   # A queued reference that becomes stale fails before any new model call.
   attached={**cursor,'kind':'chapter','text':'','offset':0,'expected_hash':current['content_hash']}
   pending=await request_run('读取这个版本的本章。',[attached])
   await call('PUT',f'/chapters/{chapter["id"]}',{'content':current['content']+'<p>新增后记。</p>'})
   model=AsyncMock()
   with patch('app.adapters.storyclaw.agent.BackendStoryPorts.model_turn',model):await execute_run(pending['id'])
   model.assert_not_called()
   self.assertEqual((await call('GET',f'/agent/runs/{pending["id"]}'))['status'],'failed')

   # The agent can edit existing canon through a version-bound, reviewable candidate.
   card=await call('POST',f'/books/{book["id"]}/config/character',{'name':'沈舟','category':'主角','description':'谨慎的旧港账房，怕连累家人。','extra_json':{'age':28}})
   from app.models import ConfigEntity
   from app.services.agent.setting_edits import setting_hash
   async with database.AsyncSessionLocal() as db:version=setting_hash(await db.get(ConfigEntity,card['id']))
   run=await request_run('把沈舟的性格改得更克制，保留身份和年龄。')
   turns=AsyncMock(side_effect=[ModelTurn(calls=[ToolCall(name='setting__read',arguments={'entity_type':'character','keyword':'沈舟'})]),
        ModelTurn(calls=[ToolCall(name='setting__update',arguments={'entity_id':card['id'],'expected_hash':version,'name':'沈舟','description':'旧港账房，情绪克制，遇到威胁先保护家人，不轻易表露恐惧。'})])])
   with patch('app.adapters.storyclaw.agent.BackendStoryPorts.model_turn',turns):await execute_run(run['id'])
   run=await call('GET',f'/agent/runs/{run["id"]}')
   self.assertEqual(run['result']['data']['kind'],'setting.update')
   async with database.AsyncSessionLocal() as db:self.assertEqual((await db.get(ConfigEntity,card['id'])).description,'谨慎的旧港账房，怕连累家人。')
   await call('POST',f'/agent/runs/{run["id"]}/adopt',{'expected_hash':version})
   async with database.AsyncSessionLocal() as db:
    edited=await db.get(ConfigEntity,card['id']);self.assertIn('情绪克制',edited.description);self.assertEqual(edited.category,'主角');self.assertEqual(edited.extra_json,{'age':28})

   # Sending a chat request can propose a plan, but a model tool cannot approve it.
   run=await request_run('安排第1到2章的连续写作，预算50积分，每章等我审阅。')
   turn=ModelTurn(calls=[ToolCall(name='plans__create',arguments={'kind':'serial','start':1,'end':2,'budget':50})])
   with patch('app.adapters.storyclaw.agent.BackendStoryPorts.model_turn',AsyncMock(return_value=turn)):await execute_run(run['id'])
   run=await call('GET',f'/agent/runs/{run["id"]}')
   self.assertEqual(run['status'],'waiting_author');self.assertEqual(run['decision']['kind'],'studio_plan')
   async with database.AsyncSessionLocal() as db:
    self.assertEqual(await db.scalar(select(func.count()).select_from(StudioTask).where(StudioTask.book_id==book['id'])),0)
   run=await call('POST',f'/agent/runs/{run["id"]}/decisions',{'decision_id':run['decision']['id'],'accept':True})
   self.assertEqual(run['status'],'waiting_task');pid=run['result']['data']['plan_id']
   async with database.AsyncSessionLocal() as db:
    task=await db.get(StudioTask,pid);self.assertFalse(task.payload['auto_adopt']);self.assertEqual(task.budget,50)
   await call('POST',f'/agent/runs/{run["id"]}/cancel')
   async with database.AsyncSessionLocal() as db:self.assertEqual((await db.get(StudioTask,pid)).status,'paused')
