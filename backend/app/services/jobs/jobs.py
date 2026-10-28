"""Bounded concurrent job consumers with SQL-wide admission and per-user fairness.

No automatic paid-generation retries: interrupted requests may have saved output.
"""
import asyncio
import logging
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from sqlalchemy import select,update,func,text,exists
from sqlalchemy.orm import aliased
from app.config import settings
from app.core.capacity import worker_slots
from app.database import AsyncSessionLocal
from app.models import Chapter
from app.models import User
from app.models.product import WorkJob
from app.services.writing.revisions import chapter_hash
from app.services.writing.revisions import current_job_id
log=logging.getLogger('storyclaw.jobs')

def now():return datetime.now(timezone.utc)

async def run_job(jid):
    from app.services.writing.chat_workflow import generate_chapter
    from app.services.writing.chat_workflow import modify_chapter
    from app.services.writing.writing_workflow import plan_chapter_scenes
    from app.services.writing.writing_workflow import analyze_book
    from app.services.knowledge.knowledge_workflow import ingest_chapter_endpoint
    from app.services.knowledge.knowledge_workflow import IngestReview
    from app.schemas import ChapterGenerateIn
    from app.schemas import AnalyzeIn
    from app.services.platform.platform import refresh_configs
    token=current_job_id.set(jid)
    from storyclaw.runtime.deps import get_stream_sink,set_stream_sink
    from app.services.agent.job_progress import emit
    previous_sink=get_stream_sink()
    async def sink(kind,payload):await emit(jid,kind,payload)
    sink.drafts_enabled=False
    set_stream_sink(sink)
    try:
        await sink('step.started',{'name':'job.validate','label':'校验任务、正文与规划版本'})
        async with AsyncSessionLocal() as db:
            job=await db.get(WorkJob,jid)
            if not job or job.status not in ('queued','running'):
                raise HTTPException(409,'任务已停止，未开始新的调用')
            from app.services.writing.revisions import assert_job_lease
            await assert_job_lease(db)
            p=job.payload
            u=await db.get(User,job.user_id)
            if not u:raise HTTPException(404,'账号不存在')
            await refresh_configs(db)
            if p.get('plan_context_hash'):
                from app.models import Book
                from app.services.agent.creation_plans import plan_context
                from storyclaw.workflows.serial import digest
                if digest(await plan_context(db,await db.get(Book,job.book_id)))!=p['plan_context_hash']:
                    raise HTTPException(409,'确认计划后作品资料已变化，请调整计划并重新确认')
            from storyclaw.skills.loader import describe_skill
            for method in p.get('method_snapshot',[]):
                if describe_skill(method['name']).get('content_hash')!=method['content_hash']:
                    raise HTTPException(409,'创作方法已升级，请核对后创建新任务；本次未调用模型')
            if job.chapter_id:
                chapter=await db.get(Chapter,job.chapter_id)
                if not chapter or chapter_hash(chapter)!=p.get('base_hash'):raise HTTPException(409,'章节已变更，任务未执行；请核对后创建新任务')
            if p.get('outline_hash'):
                from app.services.writing.planning import require_outline
                if await require_outline(db,job.book_id)!=p['outline_hash']:raise HTTPException(409,'大纲已变更，请核对后重新创建任务')
            from app.services.platform.metering import usage_scope
            await sink('step.completed',{'name':'job.validate','label':'前置条件已通过','kind':job.kind})
            from storyclaw.skills.loader import read_skill_doc
            await sink('step.completed',{'name':'skills.load','label':'加载本次创作方法','methods':[
                {**m,'document':read_skill_doc(m['name'])[:6000]} for m in p.get('method_snapshot',[])]})
            async with usage_scope(u.id,job.id,p.get('studio_plan')) as meter:
                if job.kind=='chapter-outline':
                    from app.services.writing.serial import generate_blueprint_job
                    result=await generate_blueprint_job(db,u,chapter,p.get('prompt',''))
                elif job.kind=='story-design':
                    from app.services.writing.creative_jobs import design_draft
                    result=await design_draft(db,u,job.book_id,p['design_type'],p.get('creation_plan'))
                elif job.kind=='outline':
                    from app.services.writing.outline_workflow import generate_outline
                    result=await generate_outline(job.book_id,u,db,mode=p.get('planning_mode','fixed'),creation_plan=p.get('creation_plan'))
                elif job.kind=='generate':result=await generate_chapter(job.chapter_id,ChapterGenerateIn(prompt=p['prompt']),u,db)
                elif job.kind=='revise':result=await modify_chapter(job.chapter_id,ChapterGenerateIn(prompt=p['prompt']),u,db)
                elif job.kind=='scene-plan':result=await plan_chapter_scenes(job.chapter_id,u,db)
                elif job.kind=='index':
                    result=await ingest_chapter_endpoint(job.chapter_id,IngestReview(reviewed_hash=p['reviewed_hash']),u,db)
                    if result.error:raise HTTPException(502,result.error)
                else:result=await analyze_book(job.book_id,AnalyzeIn(book_id=job.book_id,skill=p['skill'],chapter_range={'start':p['start'],'end':p['end']}),u,db)
            result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
            if isinstance(result,dict):
                result={**result,'methods':p.get('method_snapshot',[])}
                if meter.calls:result['credits_cost']=meter.spent
            # Reports/plans are useful in task details; manuscript stays in chapters.
            if job.kind in ('generate','revise'):result={k:v for k,v in result.items() if k!='content'}
        await sink('step.completed',{'name':'job.save','label':'产物已保存','credits_cost':meter.spent})
        await finish_job(jid, 'succeeded', result=result)
    except Exception as exc:
        await sink('step.failed',{'name':'job.execute','label':'任务执行中断','error':str(getattr(exc,'detail',exc))[:600]})
        raise
    finally:
        set_stream_sink(previous_sink)
        current_job_id.reset(token)

# A transaction-level global lock serializes only the short admission decision.
# Jobs release it before inference. All API/Worker processes use the same budget.
CLAIM_LOCK = 0x53434A4F4253


async def claim_job():
    """Claim one eligible job, skipping users/books already at their execution limit."""
    async with AsyncSessionLocal() as db:
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': CLAIM_LOCK})
        instant = now()
        await db.execute(update(WorkJob).where(
            WorkJob.status == 'running', WorkJob.lease_until < instant
        ).values(status='failed', lease_until=None, finished_at=instant,
                 error='执行进程中断，请先核对已保存内容，再创建新任务；系统未自动重复收费生成'))
        running_count = await db.scalar(select(func.count()).select_from(WorkJob).where(WorkJob.status == 'running'))
        if settings.worker_global_job_concurrency and running_count >= settings.worker_global_job_concurrency:
            await db.commit()
            return None
        active = aliased(WorkJob)
        user_count = select(func.count(active.id)).where(
            active.user_id == WorkJob.user_id, active.status == 'running'
        ).correlate(WorkJob).scalar_subquery()
        book_busy = exists(select(active.id).where(
            active.book_id == WorkJob.book_id, active.status == 'running'
        )).correlate(WorkJob)
        job = await db.scalar(select(WorkJob).where(
            WorkJob.status == 'queued', user_count < settings.worker_user_concurrency,
            ~book_busy
        ).order_by(WorkJob.created_at, WorkJob.id).with_for_update(skip_locked=True).limit(1))
        if job is None:
            await db.commit()
            return None
        job.status = 'running'
        job.started_at = instant
        job.lease_until = instant + timedelta(minutes=2)
        claimed = (job.id, instant)
        await db.commit()
        return claimed


async def finish_job(jid, status, *, result=None, error=None):
    """A late/expired executor cannot turn an already stopped job back into success."""
    from app.services.writing.revisions import current_job_owner
    owner = current_job_owner.get()
    async with AsyncSessionLocal() as db:
        query = update(WorkJob).where(WorkJob.id == jid)
        if owner is not None:
            if owner[0] != jid:
                raise RuntimeError('Job execution scope mismatch')
            query = query.where(WorkJob.status == 'running', WorkJob.started_at == owner[1])
            if status == 'succeeded':
                query = query.where(WorkJob.lease_until > now())
        else:
            # Explicit in-process compatibility calls have no scheduler owner.
            query = query.where(WorkJob.status.in_(['queued','running']))
        values = dict(status=status, finished_at=now(), lease_until=None, error=error)
        if result is not None:
            values['result'] = result
        updated = await db.execute(query.values(**values).returning(WorkJob.id))
        changed = updated.scalar_one_or_none() is not None
        await db.commit()
        return changed


async def heartbeat(jid, started_at):
    while True:
        await asyncio.sleep(20)
        async def renew():
            async with AsyncSessionLocal() as db:
                updated = await db.execute(update(WorkJob).where(
                    WorkJob.id == jid, WorkJob.status == 'running',
                    WorkJob.started_at == started_at, WorkJob.lease_until > now()
                ).values(lease_until=now()+timedelta(minutes=2)).returning(WorkJob.id))
                owned = updated.scalar_one_or_none() is not None
                await db.commit()
                return owned
        renewal = asyncio.create_task(renew())
        try:
            owned = await asyncio.shield(renewal)
        except asyncio.CancelledError:
            await asyncio.gather(renewal, return_exceptions=True)
            raise
        if not owned:
            raise RuntimeError('Job lease lost; executor must stop')


async def execute_claimed(jid, started_at):
    from app.services.writing.revisions import current_job_owner
    owner_token = current_job_owner.set((jid, started_at))
    pulse = asyncio.create_task(heartbeat(jid, started_at))
    execution = asyncio.create_task(run_job(jid))
    try:
        done, _ = await asyncio.wait({pulse, execution}, timeout=900,
                                     return_when=asyncio.FIRST_COMPLETED)
        if execution in done:
            await execution
        elif pulse in done:
            await pulse  # Propagate failed heartbeat instead of continuing blind inference.
        else:
            raise TimeoutError('Job execution deadline exceeded')
    except asyncio.CancelledError:
        # Finish cancellation before releasing admission, including model settlement.
        execution.cancel()
        await asyncio.gather(execution, return_exceptions=True)
        await finish_job(jid, 'failed', error='服务重启中断任务，请核对内容后重新执行')
        raise
    except Exception as exc:
        execution.cancel()
        await asyncio.gather(execution, return_exceptions=True)
        log.exception('Job failed id=%s', jid)
        error = str(exc.detail)[:500] if isinstance(exc, HTTPException) else '任务未完成，请核对正文与积分流水后重试或联系管理员'
        await finish_job(jid, 'failed', error=error)
    finally:
        for task in (pulse, execution):
            if not task.done():
                task.cancel()
        await asyncio.gather(pulse, execution, return_exceptions=True)
        current_job_owner.reset(owner_token)


async def consumer_loop():
    while True:
        try:
            # Let admission finish its short transaction before shutting down.
            # Otherwise cancellation can leak a connection/lock or orphan a claim
            # between COMMIT and starting the execution task.
            admission = asyncio.create_task(claim_job())
            try:
                claimed = await asyncio.shield(admission)
            except asyncio.CancelledError:
                outcome = (await asyncio.gather(admission, return_exceptions=True))[0]
                if isinstance(outcome, tuple):
                    async with AsyncSessionLocal() as db:
                        await db.execute(update(WorkJob).where(
                            WorkJob.id == outcome[0], WorkJob.status == 'running',
                            WorkJob.started_at == outcome[1]
                        ).values(status='queued', started_at=None, lease_until=None))
                        await db.commit()
                raise
            if claimed is None:
                await asyncio.sleep(settings.worker_poll_seconds)
                continue
            await execute_claimed(*claimed)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Queue polling failed')
            await asyncio.sleep(3)


async def queue_loop():
    """A resource-sized local pool plus cross-process user/book admission in SQL."""
    count = worker_slots()
    log.info('Job pool started slots=%s mode=%s cluster_limit=%s per_user=%s',
             count, settings.worker_job_concurrency,
             settings.worker_global_job_concurrency, settings.worker_user_concurrency)
    consumers = [asyncio.create_task(consumer_loop(), name=f'chapter-job-{slot}')
                 for slot in range(count)]
    try:
        await asyncio.gather(*consumers)
    finally:
        for task in consumers:
            task.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)
