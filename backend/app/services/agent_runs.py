"""Durable run lifecycle, author decisions and job links. No model prompts here."""
import hashlib,json
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,text,update
from storyclaw.contracts import AgentRequest
from ..database import AsyncSessionLocal
from ..models import Book,Chapter,User
from ..models.agent import AgentRun,AgentEvent
from ..models.product import WorkJob
from .revisions import chapter_hash

TERMINAL={'succeeded','partial','failed','cancelled'}

def now():return datetime.now(timezone.utc)

def out(row):
    return {k:getattr(row,k) for k in ('id','request_id','request','status','result','error','decision','job_id','event_seq','credits_cost')}

async def validate_scope(db,uid,scope):
    if scope.chapter_id and not scope.book_id:raise HTTPException(422,'章节操作必须指定作品')
    if scope.book_id:
        book=await db.get(Book,scope.book_id)
        if not book or book.user_id!=uid:raise HTTPException(404,'作品不存在')
    if scope.chapter_id:
        chapter=await db.get(Chapter,scope.chapter_id)
        if not chapter or chapter.book_id!=scope.book_id:raise HTTPException(404,'章节不存在')

async def event(db,row,kind,payload):
    row.event_seq+=1
    db.add(AgentEvent(run_id=row.id,seq=row.event_seq,type=kind,payload=payload))

async def create(request,uid,db):
    await db.execute(text('SELECT pg_advisory_xact_lock(CAST(:k AS BIGINT))'),{'k':0x414700000000+uid})
    await validate_scope(db,uid,request.scope)
    fingerprint=hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    previous=await db.scalar(select(AgentRun).where(AgentRun.user_id==uid,AgentRun.request_id==request.request_id))
    if previous:
        if previous.fingerprint!=fingerprint:raise HTTPException(409,'请求编号已用于其他目标')
        return out(previous)
    if request.entry=='command':
        from storyclaw.orchestration.capabilities import get_capability
        try:
            cap=get_capability(request.command or '');cap.schema.model_validate(request.payload)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    active=await db.scalar(select(AgentRun.id).where(AgentRun.user_id==uid,AgentRun.status.in_(['accepted','running'])))
    if active:raise HTTPException(409,'当前创作请求正在处理，请等待或到任务中心查看')
    row=AgentRun(id=str(uuid4()),user_id=uid,request_id=request.request_id,fingerprint=fingerprint,
                 request=request.model_dump(),status='accepted',event_seq=0,credits_cost=0,reserved=0)
    db.add(row);await db.flush();await event(db,row,'run.accepted',{'status':'accepted'})
    if request.entry=='command':
        row.status='running';row.lease_until=now()+timedelta(minutes=15)
    await db.commit()
    if request.entry=='command':
        await execute_run(row.id)
        await db.refresh(row)
    return out(row)

async def append(rid,uid,kind,payload):
    async with AsyncSessionLocal() as db:
        row=await db.scalar(select(AgentRun).where(AgentRun.id==rid,AgentRun.user_id==uid).with_for_update())
        if not row or row.status=='cancelled':raise HTTPException(409,'请求已取消或不存在')
        await event(db,row,kind,payload);await db.commit()

async def finish(rid,status,result=None,error=None):
    async with AsyncSessionLocal() as db:
        row=await db.scalar(select(AgentRun).where(AgentRun.id==rid).with_for_update())
        if not row or row.status=='cancelled':return
        row.status=status;row.result=result;row.error=error;row.lease_until=None
        if result:
            row.job_id=(result.get('data') or {}).get('job_id')
            if status=='waiting_author':row.decision=(result.get('data') or {}).get('decision')
        await event(db,row,'run.status',{'status':status,'result':result,'error':error});await db.commit()

async def execute_run(rid):
    from storyclaw.agent import StoryClaw
    from .story_ports.agent import BackendStoryPorts
    async with AsyncSessionLocal() as db:
        row=await db.get(AgentRun,rid)
        uid=row.user_id;request=AgentRequest.model_validate(row.request)
        # Previous visible messages are scoped to the same book, chapter and thread.
        history=[]
        if request.conversation_id:
            previous=list(await db.scalars(select(AgentRun).where(AgentRun.user_id==uid,AgentRun.id!=rid,
                AgentRun.status.in_(['succeeded','waiting_author','waiting_task','partial'])).order_by(AgentRun.created_at.desc()).limit(40)))
            for prior in reversed(previous):
                if prior.request.get('conversation_id')==request.conversation_id and prior.request.get('scope')==request.scope.model_dump():
                    history.extend([{'role':'user','content':prior.request.get('message','')},
                                    {'role':'assistant','content':(prior.result or {}).get('content','')}])
    try:
        result=await StoryClaw(BackendStoryPorts(rid,uid,request)).run(request,history=history)
        await finish(rid,result.status,result.model_dump())
    except Exception as exc:
        message=str(exc.detail) if isinstance(exc,HTTPException) else '创作请求未完成，请核对执行记录后再尝试。'
        import logging
        logging.getLogger(__name__).exception('Agent run failed id=%s',rid)
        await finish(rid,'failed',error=message[:600])

async def poll_once():
    """Claim one run; expired paid execution is not automatically retried."""
    async with AsyncSessionLocal() as db:
        expired=list(await db.scalars(select(AgentRun).where(AgentRun.status=='running',AgentRun.lease_until<now()).with_for_update()))
        for row in expired:
            row.status='failed';row.error='服务中断或执行超时；结果可能不确定，请核对回执，不会自动重试付费调用。'
            # Reservations are safely returned to platform balance; supplier cost can remain unknown.
            if row.reserved:
                await db.execute(update(User).where(User.id==row.user_id).values(credits_balance=User.credits_balance+row.reserved))
                row.reserved=0
            await event(db,row,'run.status',{'status':'failed','error':row.error})
        row=await db.scalar(select(AgentRun).where(AgentRun.status=='accepted').order_by(AgentRun.created_at).with_for_update(skip_locked=True).limit(1))
        rid=None
        if row:
            row.status='running';row.lease_until=now()+timedelta(minutes=15);rid=row.id
            await event(db,row,'run.status',{'status':'running'})
        # Reconcile linked jobs without asking a model to poll.
        waiting=list(await db.scalars(select(AgentRun).where(AgentRun.status=='waiting_task').limit(100).with_for_update(skip_locked=True)))
        for r in waiting:
            job=await db.get(WorkJob,r.job_id)
            if job and job.status in ('succeeded','failed','cancelled'):
                r.status=job.status;r.result={**(r.result or {}),'status':job.status,
                    'content':'任务已完成，请在对应面板或任务中心核对结果。' if job.status=='succeeded' else (job.error or '任务已取消'),
                    'data':{'job_id':job.id,'job_result':job.result}};r.error=job.error
                await event(db,r,'run.status',{'status':r.status,'result':r.result})
        await db.commit()
    if rid:await execute_run(rid)
    return bool(rid)
