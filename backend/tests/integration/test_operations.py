"""Operational gap closure: private blobs, causal knowledge, delivery and reconciliation."""
import hashlib,unittest,io
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock,patch
import httpx
from storyclaw.knowledge import knowledge_view
from storyclaw.knowledge import alias_map
from storyclaw.knowledge import validate_causes
from tests.integration import test_studio as studio_tests
class NarrativePolicies(unittest.TestCase):
 def test_alias_secret_time_and_claims(self):
  facts=[{'id':'a','subject':'老沈','statement':'知道密道','kind':'belief','holder':'老沈','known_by':['阿照'],'valid_from':2,'valid_until':4,'certainty':'claim','review_status':'confirmed'}, {'id':'b','subject':'沈照','statement':'未来事件','kind':'event','known_by':['沈照'],'valid_from':8}]
  entities=[{'name':'沈照','aliases':['阿照','老沈']}]
  view=knowledge_view(facts,chapter_number=3,persona='阿照',entities=entities)
  self.assertEqual(view['facts'][0]['holder'],'沈照');self.assertEqual(len(view['facts']),1);self.assertEqual(view['facts'][0]['certainty'],'claim')
  self.assertEqual(knowledge_view(facts,chapter_number=3,persona='外人',entities=entities)['withheld'],1)
  self.assertEqual(knowledge_view(facts,chapter_number=5,persona='阿照',entities=entities)['facts'],[])
  with self.assertRaises(ValueError):alias_map([*entities,{'name':'另一人','aliases':['阿照']}])
 def test_causal_cycle_and_foreign_id(self):
  validate_causes('b',['a'],[{'id':'a','causes':[]}])
  with self.assertRaises(ValueError):validate_causes('b',['a'],[{'id':'a','causes':['b']},{'id':'b','causes':[]}])
  with self.assertRaises(ValueError):validate_causes('b',['foreign'],[])
class BlobProtocol(unittest.IsolatedAsyncioTestCase):
 async def test_signed_private_roundtrip_and_fail_closed(self):
  from app.services.storage.blob_store import S3Store
  objects={};bucket=False
  def route(req):
   nonlocal bucket
   self.assertTrue(req.headers['Authorization'].startswith('AWS4-HMAC-SHA256'))
   self.assertEqual(req.headers['x-amz-content-sha256'],hashlib.sha256(req.content).hexdigest())
   if req.url.path=='/story-test':
    if req.method=='PUT':bucket=True;return httpx.Response(200)
    return httpx.Response(200 if bucket else 404)
   key=req.url.path
   if req.method=='PUT':objects[key]=req.content;return httpx.Response(200)
   if req.method=='DELETE':objects.pop(key,None);return httpx.Response(204)
   return httpx.Response(200,content=objects[key]) if key in objects else httpx.Response(404)
  store=S3Store('http://storage:9000','story-test','test-access','test-secret',transport=httpx.MockTransport(route))
  await store.put('private/a b.txt','测试稿'.encode());self.assertEqual(await store.get('private/a b.txt'),'测试稿'.encode())
  await store.delete('private/a b.txt');await store.delete('private/a b.txt')
  from fastapi import HTTPException
  with self.assertRaises(HTTPException):await store.get('private/a b.txt')
# Reuse test setup helpers without inheriting the entire suite again.
class OperationsIntegration(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=studio_tests.StudioIntegration.asyncSetUp
 asyncTearDown=studio_tests.StudioIntegration.asyncTearDown
 req=studio_tests.StudioIntegration.req
 upload=studio_tests.StudioIntegration.upload
 async def test_incremental_prefix_invalidates_only_suffix(self):
  from app.services.knowledge.history_prefix import history_digest
  from app.models.operations import HistoryPrefix
  from app.models import Chapter
  c1=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'第一章'})
  c2=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'第二章'})
  async with self.db() as db:
   r1=await history_digest(db,self.bid,1);r2=await history_digest(db,self.bid,2);await db.commit()
  await self.req('PUT',f'/chapters/{c2["id"]}',{'content':'第二章的新内容'})
  async with self.db() as db:
   self.assertEqual((await db.get(HistoryPrefix,(self.bid,1))).digest,r1)
   self.assertIsNone(await db.get(HistoryPrefix,(self.bid,2)))
   self.assertNotEqual(await history_digest(db,self.bid,2),r2);await db.commit()
  await self.req('DELETE',f'/chapters/{c1["id"]}')
  async with self.db() as db:self.assertIsNone(await db.get(HistoryPrefix,(self.bid,1)))
 async def test_usage_receipt_idempotent_and_no_silent_charge(self):
  from app.models import User
  from app.models.studio import ModelCall
  async with self.db() as db:
   admin=await db.get(User,self.uid);admin.is_admin=True
   call=ModelCall(id=str(uuid4()),user_id=self.uid,model='embedding:test',status='unknown',reserved=0,cost=0,usage={'pricing':{'embedding_rate':1}},lease_until=datetime.now(timezone.utc));db.add(call);cid=call.id;await db.commit()
  await self.req('GET','/admin/model-calls');await self.req('GET','/admin/cleanup-tasks')
  body={'request_id':str(uuid4()),'input_tokens':2500,'output_tokens':0,'supplier_reference':'supplier-123','note':'已核对供应商账单','adjust_user_balance':False}
  response=await self.req('POST',f'/admin/model-calls/{cid}/reconcile',body);self.assertEqual(response['delta'],0)
  duplicate=await self.req('POST',f'/admin/model-calls/{cid}/reconcile',body);self.assertTrue(duplicate['idempotent'])
  await self.req('POST',f'/admin/model-calls/{cid}/reconcile',{**body,'input_tokens':3000},status=409)
  async with self.db() as db:
   self.assertEqual((await db.get(User,self.uid)).credits_balance,10000);self.assertEqual((await db.get(ModelCall,cid)).usage['reconciled_cost'],3)
 async def test_blob_migration_preserves_original_and_cleanup_checks_reference(self):
  from app.services.storage.blob_store import migrate_originals
  from app.services.storage.blob_store import read_original
  from app.services.storage.cleanup import poll_once
  from app.models.studio import StorySource
  from app.models.operations import SourceBlob
  from app.models.operations import CleanupTask
  from app.config import settings
  from sqlalchemy import select
  source=await self.upload();objects={}
  service=AsyncMock()
  async def put(key,value):objects[key]=value
  async def get(key):return objects[key]
  service.put.side_effect=put;service.get.side_effect=get
  with patch.object(settings,'source_storage_backend','s3'),patch('app.services.storage.blob_store.store',return_value=service):
   # Migrate just this fixture, not unrelated test rows.
   from app.services.storage.blob_store import write_original
   async with self.db() as db:
    row=await db.get(StorySource,source['id']);original=row.original;await write_original(db,row,original);await db.commit()
   async with self.db() as db:
    row=await db.get(StorySource,source['id']);self.assertEqual(row.original,b'');self.assertEqual(await read_original(db,row),original)
    task=await db.scalar(select(CleanupTask).where(CleanupTask.payload['key'].as_string().contains(source['id'])));task.due_at=datetime.now(timezone.utc)-timedelta(seconds=1);tid=task.id;await db.commit()
   await poll_once();service.delete.assert_not_awaited()
   async with self.db() as db:self.assertEqual((await db.get(CleanupTask,tid)).status,'retained')
 async def test_scheduled_snapshot_delivery_exactly_once_and_cancel(self):
  from app.services.publishing.release_delivery import poll_once
  from app.models.operations import ReleaseDelivery
  from app.models.product import Publication
  c=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'第一章'})
  await self.req('PUT',f'/chapters/{c["id"]}',{'content':'批准的固定稿。'})
  r=await self.req('POST',f'/books/{self.bid}/releases',{'platform':'storyclaw','rights_confirmed':True,'ai_policy_confirmed':True})
  await self.req('POST',f'/releases/{r["id"]}/schedule',{'snapshot_hash':r['hash'],'confirmed':True,'due_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()})
  await self.req('PUT',f'/chapters/{c["id"]}',{'content':'未批准的新稿。'})
  async with self.db() as db:
   row=await db.get(ReleaseDelivery,r['id']);row.due_at=datetime.now(timezone.utc)-timedelta(seconds=1);await db.commit()
  self.assertTrue(await poll_once());self.assertFalse(await poll_once())
  async with self.db() as db:
   pub=await db.get(Publication,self.bid);self.assertIn('批准的固定稿',str(pub.snapshot));self.assertNotIn('未批准的新稿',str(pub.snapshot))
  await self.req('DELETE',f'/releases/{r["id"]}/schedule',status=409)
 async def test_fact_alias_focus_review_and_stale_source(self):
  from app.services.knowledge.index_manifest import stage
  from app.services.knowledge.index_manifest import activate
  from app.models import Chapter
  from app.services.writing.revisions import chapter_hash
  c=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'第一章'})
  await self.req('PUT',f'/chapters/{c["id"]}',{'content':'甲知道灯的秘密。乙还不知道。'})
  async with self.db() as db:
   ch=await db.get(Chapter,c['id']);h=chapter_hash(ch);m=await stage(db,ch,h)
   result={'chunks':1,'stores':{'vector':'milvus','graph':'neo4j'},'memory':{'facts':[{'subject':'甲','statement':'知道灯的秘密','quote':'甲知道灯的秘密','kind':'state','certainty':'observed','known_by':['甲']} ]}}
   self.assertTrue(await activate(db,m,ch,result,h));ch.rag_status='loaded';await db.commit()
  await self.req('POST',f'/books/{self.bid}/narrative/entities',{'name':'甲','aliases':['老甲']})
  await self.req('POST',f'/books/{self.bid}/narrative/entities',{'name':'另一人','aliases':['老甲']},status=409)
  hidden=await self.req('GET',f'/books/{self.bid}/narrative/view?before=2&persona=乙');self.assertEqual(hidden['facts'],[])
  visible=await self.req('GET',f'/books/{self.bid}/narrative/view?before=2&persona=老甲');self.assertEqual(len(visible['facts']),1)
  f=(await self.req('GET',f'/books/{self.bid}/narrative/facts'))[0]
  body={k:f[k] for k in ('subject','statement','quote','kind','certainty','holder','known_by','public','story_time','causes','valid_until','review_status','version')};body['review_status']='confirmed'
  await self.req('PUT',f'/books/{self.bid}/narrative/facts/{f["id"]}',body)
  await self.req('PUT',f'/books/{self.bid}/narrative/facts/{f["id"]}',body,status=409)
  await self.req('PUT',f'/books/{self.bid}/narrative/focus/{c["id"]}',{'persona':'乙'})
  await self.req('PUT',f'/chapters/{c["id"]}',{'content':'甲忘记了灯的秘密。'})
  self.assertEqual((await self.req('GET',f'/books/{self.bid}/narrative/view?before=2&persona=甲'))['facts'],[])
 async def test_lead_loop_uses_same_meter_with_own_budget_and_unknown_usage(self):
  from app.services.platform.metering import usage_scope
  from app.models.agent import AgentRun
  from app.models.studio import ModelCall
  from fastapi import HTTPException
  from sqlalchemy import select
  rid=str(uuid4())
  async with self.db() as db:
   db.add(AgentRun(id=rid,user_id=self.uid,request_id=str(uuid4()),fingerprint='f'*64,request={},status='running',credits_cost=60,event_seq=0,reserved=0));await db.commit()
  async with usage_scope(self.uid,run_id=rid) as meter:
   with self.assertRaises(HTTPException):await meter.reserve('embedding:test',50000,0)
   cid=await meter.reserve('embedding:test',100,0)
   self.assertEqual(await meter.settle(cid,{'input_tokens':100,'output_tokens':0},True),1)
   other=await meter.reserve('embedding:test',100,0)
   self.assertEqual(await meter.settle(other,{'supplier_request_id':'request-without-usage'},False),0)
  async with self.db() as db:
   self.assertEqual((await db.get(AgentRun,rid)).credits_cost,61)
   call=await db.get(ModelCall,other);self.assertEqual(call.status,'unknown');self.assertFalse(call.usage['known'])
 async def test_invalid_ideation_refunds_metered_calls_and_preserves_usage(self):
  from storyclaw.models.metering import active_meter
  from app.models import User
  from app.models.studio import ModelCall
  from sqlalchemy import select
  async def malformed(*args,**kwargs):
   meter=active_meter.get();self.assertIsNotNone(meter)
   cid=await meter.reserve('embedding:format-test',100,0);meter.call_ids.append(cid)
   meter.spent+=await meter.settle(cid,{'input_tokens':100,'output_tokens':0},True);meter.calls+=1
   raise ValueError('Synthetic invalid JSON')
  with patch('storyclaw.workflows.ideation.engine.generate_discussion',side_effect=malformed):
   error=await self.req('POST','/assist/ideation',{'request_id':str(uuid4()),'mode':'proposal','messages':[{'role':'user','content':'测试格式失败不扣积分'}]},status=502)
  self.assertIn('未扣积分',str(error))
  async with self.db() as db:
   self.assertEqual((await db.get(User,self.uid)).credits_balance,10000)
   row=await db.scalar(select(ModelCall).where(ModelCall.user_id==self.uid));self.assertTrue(row.usage['format_refunded']);self.assertEqual(row.cost,0);self.assertEqual(row.usage['input_tokens'],100)
 async def test_failed_candidate_adoption_needs_current_hash(self):
  from app.models.product import WorkJob
  c=await self.req('POST',f'/chapters/books/{self.bid}',{'title':'候选章节'})
  jid=str(uuid4())
  async with self.db() as db:
   db.add(WorkJob(id=jid,user_id=self.uid,book_id=self.bid,chapter_id=c['id'],kind='generate',request_id=str(uuid4()),payload={},status='failed',result={'candidate':{'content':'中断前保留下来的正文候选。','chapter_id':c['id'],'base_hash':c['content_hash'],'adopted':False}}));await db.commit()
  await self.req('POST',f'/jobs/{jid}/candidate/adopt',{'expected_hash':'0'*64},status=409)
  await self.req('POST',f'/jobs/{jid}/candidate/adopt',{'expected_hash':c['content_hash']})
  self.assertEqual((await self.req('GET',f'/chapters/{c["id"]}'))['rag_status'],'pending')
  await self.req('POST',f'/jobs/{jid}/candidate/adopt',{'expected_hash':c['content_hash']},status=409)

class InterruptedWriter(unittest.IsolatedAsyncioTestCase):
 async def test_quota_failure_keeps_previous_draft_and_stops_review(self):
  from storyclaw.agents.nodes.writer import _writer_write
  from storyclaw.agents.nodes.reviewer import reviewer
  class Quota(Exception):
   status_code=429
   body={'error':{'code':'1113'}}
  state={'draft_content':'已有完整候选，不应因下一次调用失败而丢失。','context':{'chapter_meta':{'per_chapter_words':2500}},'review_feedback':'补足字数'}
  with patch('storyclaw.agents.nodes.writer.tool_loop',AsyncMock(return_value='')),patch('storyclaw.agents.nodes.writer._respond_aware',AsyncMock(side_effect=Quota())):
   result=await _writer_write(state)
  self.assertEqual(result['draft_content'],state['draft_content']);self.assertEqual(result['error_code'],'supplier_quota')
  with patch('storyclaw.agents.nodes.reviewer.llm_respond',AsyncMock()) as model:
   self.assertEqual((await reviewer({**state,**result}))['status'],'error');model.assert_not_awaited()
 async def test_checkpoint_recovery_rejects_foreign_scope(self):
  from types import SimpleNamespace
  from storyclaw.runtime.execution import recover_candidate
  from storyclaw.runtime.execution import checkpoint_key
  async def snapshots(*args,**kwargs):
   yield SimpleNamespace(values={'user_id':9,'book_id':5,'chapter_id':8,'draft_content':'他人内容'})
   yield SimpleNamespace(values={'user_id':1,'book_id':5,'chapter_id':8,'draft_content':'本范围候选'})
  graph=unittest.mock.MagicMock();graph.aget_state_history=snapshots
  with patch('storyclaw.runtime.execution.get_graph',return_value=graph):result=await recover_candidate('known-thread',1,5,8)
  self.assertEqual(result['content'],'本范围候选')
  self.assertNotEqual(checkpoint_key({'user_id':1,'book_id':5},'same'),checkpoint_key({'user_id':2,'book_id':5},'same'))
