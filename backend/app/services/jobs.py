"""Durable single-consumer queue; SQL claiming also supports multiple API instances.

No automatic paid-generation retries: interrupted requests may have saved output.
"""
import asyncio
import logging
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from sqlalchemy import select,update
from ..database import AsyncSessionLocal
from ..models import Chapter,User
from ..models.product import WorkJob
from .revisions import chapter_hash,current_job_id
log=logging.getLogger('storyclaw.jobs')

def now():return datetime.now(timezone.utc)

async def run_job(jid):
    from ..api.chat import generate_chapter
    from ..api.writing import plan_chapter_scenes,analyze_book
    from ..api.rag import ingest_chapter_endpoint,IngestReview
    from ..schemas import ChapterGenerateIn,AnalyzeIn
    from .platform import refresh_configs
    token=current_job_id.set(jid)
    try:
        async with AsyncSessionLocal() as db:
            job=await db.get(WorkJob,jid);p=job.payload
            u=await db.get(User,job.user_id)
            if not u:raise HTTPException(404,'账号不存在')
            await refresh_configs(db)
            if job.chapter_id:
                chapter=await db.get(Chapter,job.chapter_id)
                if not chapter or chapter_hash(chapter)!=p.get('base_hash'):raise HTTPException(409,'章节已变更，任务未执行；请核对后创建新任务')
            if p.get('outline_hash'):
                from .planning import require_outline
                if await require_outline(db,job.book_id)!=p['outline_hash']:raise HTTPException(409,'大纲已变更，请核对后重新创建任务')
            if job.kind=='chapter-outline':
                from .serial import generate_blueprint_job
                result=await generate_blueprint_job(db,u,chapter,p.get('prompt',''))
            elif job.kind=='story-design':
                from .creative_jobs import design_draft
                result=await design_draft(db,u,job.book_id,p['design_type'])
            elif job.kind=='outline':
                from ..api.outlines import generate_outline
                result=await generate_outline(job.book_id,u,db,mode=p.get('planning_mode','fixed'))
            elif job.kind=='generate':result=await generate_chapter(job.chapter_id,ChapterGenerateIn(prompt=p['prompt']),u,db)
            elif job.kind=='scene-plan':result=await plan_chapter_scenes(job.chapter_id,u,db)
            elif job.kind=='index':
                result=await ingest_chapter_endpoint(job.chapter_id,IngestReview(reviewed_hash=p['reviewed_hash']),u,db)
                if result.error:raise HTTPException(502,result.error)
            else:result=await analyze_book(job.book_id,AnalyzeIn(book_id=job.book_id,skill=p['skill'],chapter_range={'start':p['start'],'end':p['end']}),u,db)
            result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
            # Reports/plans are useful in task details; manuscript stays in chapters.
            if job.kind=='generate':result={k:v for k,v in result.items() if k!='content'}
        async with AsyncSessionLocal() as db:
            j=await db.get(WorkJob,jid);j.status='succeeded';j.result=result;j.finished_at=now();j.lease_until=None;await db.commit()
    finally:current_job_id.reset(token)

async def heartbeat(jid):
    while True:
        await asyncio.sleep(20)
        async with AsyncSessionLocal() as db:
            await db.execute(update(WorkJob).where(WorkJob.id==jid,WorkJob.status=='running').values(lease_until=now()+timedelta(minutes=2)))
            await db.commit()

async def queue_loop():
    while True:
        jid=None
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(update(WorkJob).where(WorkJob.status=='running',WorkJob.lease_until<now()).values(status='failed',error='执行进程中断，请先核对已保存内容，再创建新任务；系统未自动重复收费生成',finished_at=now()))
                j=await db.scalar(select(WorkJob).where(WorkJob.status=='queued').order_by(WorkJob.created_at).with_for_update(skip_locked=True).limit(1))
                if j:j.status='running';j.started_at=now();j.lease_until=now()+timedelta(minutes=2);jid=j.id
                await db.commit()
            if not jid:
                from .agent_runs import poll_once
                if not await poll_once():await asyncio.sleep(2)
                continue
            pulse=asyncio.create_task(heartbeat(jid))
            try:
                await asyncio.wait_for(run_job(jid),timeout=900)
            except asyncio.CancelledError:
                async with AsyncSessionLocal() as db:
                    j=await db.get(WorkJob,jid);j.status='failed';j.error='服务重启中断任务，请核对内容后重新执行';j.finished_at=now();await db.commit()
                raise
            except Exception as exc:
                log.exception('Job failed id=%s',jid)
                error=str(exc.detail)[:500] if isinstance(exc,HTTPException) else '任务未完成，请核对正文与积分流水后重试或联系管理员'
                async with AsyncSessionLocal() as db:
                    j=await db.get(WorkJob,jid);j.status='failed';j.error=error;j.finished_at=now();j.lease_until=None;await db.commit()
            finally:
                pulse.cancel()
                try:await pulse
                except asyncio.CancelledError:pass
        except asyncio.CancelledError:raise
        except Exception:
            log.exception('Queue polling failed');await asyncio.sleep(3)
