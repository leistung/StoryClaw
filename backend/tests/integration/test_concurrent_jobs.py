"""Real PostgreSQL admission/overlap tests; shared model is deterministic and never networked."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage

class ConcurrentJobs(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url=os.environ.get('DATABASE_URL','')
        if not url.endswith('/storyclaw_refactor_test'):
            self.skipTest('isolated test database required')
        import app.database as database
        await database.engine.dispose()
        database.engine=create_async_engine(url,poolclass=NullPool)
        database.AsyncSessionLocal.configure(bind=database.engine)
        self.db=database.AsyncSessionLocal
        from app.models import Base
        from app.models.product import WorkJob
        from app.models.platform import PlatformConfig
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.db() as db:
            # Only this explicitly named disposable DB is touched, never the live platform.
            await db.execute(update(WorkJob).where(WorkJob.status.in_(['queued','running'])).values(status='cancelled'))
            price={'pricing':{'shared-test-model':{'input_price':1,'output_price':1,'enabled':True}},'defaults':{'price_base':'per_1k_tokens'}}
            await db.execute(insert(PlatformConfig).values(key='pricing.yaml',value=price).on_conflict_do_update(index_elements=['key'],set_={'value':price}))
            await db.commit()
        from app.config import settings
        self.config=patch.multiple(settings,worker_job_concurrency='3',worker_global_job_concurrency=0,worker_user_concurrency=1,worker_poll_seconds=.05)
        self.config.start();self.addCleanup(self.config.stop)
        self.jobs=[];self.users=[]

    async def asyncTearDown(self):
        if hasattr(self,'db'):
            from app.models.product import WorkJob
            async with self.db() as db:
                await db.execute(update(WorkJob).where(WorkJob.id.in_(self.jobs),WorkJob.status.in_(['queued','running'])).values(status='cancelled'))
                await db.commit()

    async def job(self, *, user=None, book=None):
        from app.models import User,Book,Chapter
        from app.models.product import WorkJob
        from app.services.writing.revisions import chapter_hash
        async with self.db() as db:
            if user is None:
                u=User(username='concurrent-'+uuid4().hex[:12],password_hash='not-a-login-password',version='business',credits_balance=100)
                db.add(u);await db.flush();user=u.id;self.users.append(user)
            if book is None:
                b=Book(user_id=user,title='独立并发样书',genre='玄幻');db.add(b);await db.flush();book=b.id
            c=Chapter(book_id=book,title='当前章',number=len(self.jobs)+1,content='',word_count=0)
            db.add(c);await db.flush()
            j=WorkJob(id=str(uuid4()),user_id=user,book_id=book,chapter_id=c.id,kind='generate',request_id=str(uuid4()),payload={'prompt':'test','base_hash':chapter_hash(c),'method_snapshot':[]})
            db.add(j);await db.commit();self.jobs.append(j.id)
            return j.id,user,book,c.id

    async def states(self):
        from app.models.product import WorkJob
        async with self.db() as db:
            return dict((await db.execute(select(WorkJob.id,WorkJob.status).where(WorkJob.id.in_(self.jobs)))).all())

    async def terminal(self):
        async def wait():
            while True:
                values=await self.states()
                if all(v in ('succeeded','failed','cancelled') for v in values.values()):return values
                await asyncio.sleep(.03)
        return await asyncio.wait_for(wait(),10)

    async def test_three_users_really_overlap_on_one_model_with_isolated_usage(self):
        from app.services.jobs.jobs import queue_loop
        from app.services.writing.revisions import current_job_id,current_job_owner
        from storyclaw.models.metering import active_meter,MeteredModel
        fixtures=[await self.job() for _ in range(3)]
        expected={c:(j,u) for j,u,b,c in fixtures};entered=[];all_started=asyncio.Event();release=asyncio.Event()
        class SharedModel:
            max_tokens=32
            async def ainvoke(inner,messages,**kwargs):
                entered.append(messages[0].content)
                if len(entered)==3:all_started.set()
                await release.wait()
                return AIMessage(content=messages[0].content,usage_metadata={'input_tokens':10,'output_tokens':10,'total_tokens':20})
        shared=SharedModel();meters=[]
        async def generate(cid,data,u,db):
            jid,uid=expected[cid]
            self.assertEqual(u.id,uid);self.assertEqual(current_job_id.get(),jid)
            self.assertEqual(current_job_owner.get()[0],jid)
            meter=active_meter.get();meters.append(meter)
            response=await MeteredModel(shared,'shared-test-model',meter).ainvoke([HumanMessage(content=f'{uid}:{cid}')])
            self.assertEqual(response.content,f'{uid}:{cid}')
            return {'content':response.content,'word_count':10}
        with patch('app.services.writing.chat_workflow.generate_chapter',generate):
            pool=asyncio.create_task(queue_loop())
            try:
                await asyncio.wait_for(all_started.wait(),5)
                self.assertEqual(set((await self.states()).values()),{'running'})
                self.assertEqual(len({id(m) for m in meters}),3)
                release.set();self.assertEqual(set((await self.terminal()).values()),{'succeeded'})
            finally:
                pool.cancel();await asyncio.gather(pool,return_exceptions=True)
        from app.models import User
        from app.models.studio import ModelCall
        async with self.db() as db:
            calls=list(await db.scalars(select(ModelCall).where(ModelCall.job_id.in_(self.jobs))))
            self.assertEqual({(c.job_id,c.user_id,c.model,c.cost) for c in calls},{(j,u,'shared-test-model',1) for j,u,b,cid in fixtures})
            for uid in self.users:self.assertEqual((await db.get(User,uid)).credits_balance,99)
        self.assertIsNone(active_meter.get());self.assertIsNone(current_job_id.get());self.assertIsNone(current_job_owner.get())

    async def test_sql_global_limit_survives_many_simultaneous_claimers(self):
        from app.services.jobs.jobs import claim_job
        from app.config import settings
        for _ in range(5):await self.job()
        with patch.object(settings,'worker_global_job_concurrency',2):
            claimed=await asyncio.gather(*(claim_job() for _ in range(12)))
        ids=[c[0] for c in claimed if c]
        self.assertEqual(len(ids),2);self.assertEqual(len(set(ids)),2)

    async def test_busy_user_does_not_block_another_user(self):
        from app.services.jobs.jobs import claim_job
        a=await self.job();await self.job(user=a[1]);b=await self.job()
        first=await claim_job();second=await claim_job()
        self.assertEqual(first[0],a[0]);self.assertEqual(second[0],b[0])
        self.assertIsNone(await claim_job())

    async def test_same_book_is_serial_even_if_user_has_multiple_slots(self):
        from app.services.jobs.jobs import claim_job
        from app.config import settings
        a=await self.job();await self.job(user=a[1],book=a[2]);b=await self.job(user=a[1])
        with patch.object(settings,'worker_user_concurrency',3):
            claims=await asyncio.gather(*(claim_job() for _ in range(6)))
        self.assertEqual({c[0] for c in claims if c},{a[0],b[0]})

    async def test_one_user_failure_does_not_stop_another(self):
        from app.services.jobs.jobs import queue_loop
        a=await self.job();b=await self.job();entered=asyncio.Event()
        async def generate(cid,data,u,db):
            if u.id==a[1]:raise HTTPException(502,'模拟单用户失败')
            entered.set();return {'word_count':1}
        with patch('app.services.writing.chat_workflow.generate_chapter',generate):
            pool=asyncio.create_task(queue_loop())
            try:
                states=await self.terminal()
                self.assertEqual(states[a[0]],'failed');self.assertEqual(states[b[0]],'succeeded');self.assertTrue(entered.is_set())
            finally:
                pool.cancel();await asyncio.gather(pool,return_exceptions=True)

    async def test_pool_shutdown_stops_children_and_preserves_unclaimed_jobs(self):
        from app.services.jobs.jobs import queue_loop
        from app.config import settings
        for _ in range(3):await self.job()
        started=asyncio.Event();calls=[]
        async def generate(*args):
            calls.append(args[0])
            if len(calls)==2:started.set()
            await asyncio.Event().wait()
        with patch.object(settings,'worker_job_concurrency','2'),patch('app.services.writing.chat_workflow.generate_chapter',generate):
            pool=asyncio.create_task(queue_loop())
            try:await asyncio.wait_for(started.wait(),5)
            finally:pool.cancel();await asyncio.gather(pool,return_exceptions=True)
        states=list((await self.states()).values())
        self.assertEqual(states.count('failed'),2);self.assertEqual(states.count('queued'),1)

    async def test_expired_executor_cannot_reserve_or_finish_success(self):
        from app.services.jobs.jobs import claim_job,finish_job
        from app.services.writing.revisions import current_job_owner
        from app.services.platform.metering import usage_scope
        from app.models.product import WorkJob
        a=await self.job();claim=await claim_job()
        from app.services.platform.platform import refresh_configs
        async with self.db() as db:await refresh_configs(db)
        async with self.db() as db:
            await db.execute(update(WorkJob).where(WorkJob.id==a[0]).values(lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)))
            await db.commit()
        await claim_job() # Marks expired work failed; it never retries paid generation.
        token=current_job_owner.set(claim)
        try:
            self.assertFalse(await finish_job(a[0],'succeeded',result={'wrong':True}))
            async with usage_scope(a[1],a[0]) as meter:
                with self.assertRaises(HTTPException) as raised:await meter.reserve('shared-test-model',10,10)
                self.assertEqual(raised.exception.status_code,409)
        finally:current_job_owner.reset(token)
        self.assertEqual((await self.states())[a[0]],'failed')

    async def test_shutdown_during_admission_returns_unstarted_claim_to_queue(self):
        from app.services.jobs.jobs import consumer_loop,claim_job
        a=await self.job();claimed=asyncio.Event();release=asyncio.Event()
        async def delayed_claim():
            result=await claim_job();claimed.set();await release.wait();return result
        with patch('app.services.jobs.jobs.claim_job',delayed_claim):
            consumer=asyncio.create_task(consumer_loop())
            await asyncio.wait_for(claimed.wait(),5)
            consumer.cancel();release.set()
            await asyncio.gather(consumer,return_exceptions=True)
        self.assertEqual((await self.states())[a[0]],'queued')
