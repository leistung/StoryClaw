"""Durable run lifecycle, author decisions and job links. No model prompts here."""
import hashlib,json,asyncio,logging
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,text,update,or_,and_
from storyclaw.contracts import AgentRequest
from app.database import AsyncSessionLocal
from app.models import Book
from app.models import Chapter
from app.models import User
from app.models.agent import AgentRun
from app.models.agent import AgentEvent
from app.models.product import WorkJob
from app.services.writing.revisions import chapter_hash

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
    from app.services.agent.manuscript_references import validate_references
    await validate_references(db,request)
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
    inline=request.entry=='command' and cap.name not in ('framework.draft','setting.draft') and (cap.job_kind is not None or cap.name in ('project.status','material.read','memory.search'))
    if inline:
        row.status='running';row.lease_until=now()+timedelta(minutes=15)
    await db.commit()
    if inline:
        await execute_run(row.id)
        await db.refresh(row)
    return out(row)

async def append(rid,uid,kind,payload):
    async with AsyncSessionLocal() as db:
        row=await db.scalar(select(AgentRun).where(AgentRun.id==rid,AgentRun.user_id==uid).with_for_update())
        if not row or row.status=='cancelled':raise HTTPException(409,'请求已取消或不存在')
        await event(db,row,kind,payload);await db.commit()

async def revise_creation(db,uid,bid,rid,feedback,current_rid):
    row=await db.scalar(select(AgentRun).where(AgentRun.id==rid,AgentRun.user_id==uid).with_for_update())
    if not row or row.request.get('scope',{}).get('book_id')!=bid:raise HTTPException(404,'本作品的生成计划不存在')
    if row.status!='waiting_author' or (row.decision or {}).get('kind')!='creation_plan':raise ValueError('此生成计划已执行或失效，请重新拟订')
    from uuid import uuid5,NAMESPACE_URL
    submitted=await db.scalar(select(WorkJob.id).where(WorkJob.user_id==uid,WorkJob.request_id==str(uuid5(NAMESPACE_URL,row.id+':'+row.decision['command']))))
    if submitted:raise ValueError('此计划已经提交任务，不能再调整')
    row.decision={**row.decision,'feedback':feedback};row.status='accepted';row.result=None;row.error=None;row.lease_until=None
    await event(db,row,'plan.revised',{'feedback':feedback,'label':'已收到对话补充，重新拟订计划','source_run':current_rid})
    await db.commit()

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
    from storyclaw.agents.lead_agent.agent import StoryClaw
    from app.adapters.storyclaw.agent import BackendStoryPorts
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
        if request.references:
            from app.services.agent.manuscript_references import validate_references
            async with AsyncSessionLocal() as db:await validate_references(db,request)
        result=await StoryClaw(BackendStoryPorts(rid,uid,request)).run(request,history=history)
        await finish(rid,result.status,result.model_dump())
    except Exception as exc:
        message=str(exc.detail) if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,ValueError) else '创作请求未完成，请核对执行记录后再尝试。'
        import logging
        logging.getLogger(__name__).exception('Agent run failed id=%s',rid)
        await finish(rid,'failed',error=message[:600])

async def poll_once():
    """Claim one run; expired paid execution is not automatically retried."""
    async with AsyncSessionLocal() as db:
        expired=list(await db.scalars(select(AgentRun).where(AgentRun.lease_until<now(),or_(AgentRun.status=='running',AgentRun.reserved>0)).with_for_update()))
        for row in expired:
            if row.status!='cancelled':row.status='failed'
            row.error='服务中断或执行超时；结果可能不确定，请核对回执，不会自动重试付费调用。'
            # Reservations are safely returned to platform balance; supplier cost can remain unknown.
            if row.reserved:
                await db.execute(update(User).where(User.id==row.user_id).values(credits_balance=User.credits_balance+row.reserved))
                row.reserved=0
            await event(db,row,'run.status',{'status':row.status,'error':row.error})
        row=await db.scalar(select(AgentRun).where(AgentRun.status=='accepted').order_by(AgentRun.created_at).with_for_update(skip_locked=True).limit(1))
        rid=None
        if row:
            row.status='running';row.lease_until=now()+timedelta(minutes=15);rid=row.id
            await event(db,row,'run.status',{'status':'running'})
        # Reconcile linked jobs without asking a model to poll.
        waiting=list(await db.scalars(select(AgentRun).where(AgentRun.status=='waiting_task').limit(100).with_for_update(skip_locked=True)))
        for r in waiting:
            plan_id=((r.result or {}).get('data') or {}).get('plan_id')
            if plan_id:
                from app.models.studio import StudioTask
                task=await db.get(StudioTask,plan_id)
                if task and ((r.result or {}).get('data') or {}).get('plan_status')!=task.status:
                    r.status={'paused':'partial','failed':'failed','succeeded':'succeeded','cancelled':'cancelled'}.get(task.status,'waiting_task')
                    r.result={'status':r.status,'content':task.error or {'succeeded':'计划已完成','waiting_author':'计划等待你审阅章纲或正文，请到对应面板核对后，在对话中提出恢复需求。'}.get(task.status,'计划按已确认范围执行中'),
                        'data':{'plan_id':task.id,'plan_status':task.status,'phase':task.result,'spent':task.spent,'budget':task.budget}}
                    await event(db,r,'run.status',{'status':r.status,'result':r.result})
                continue
            job=await db.get(WorkJob,r.job_id) if r.job_id else None
            if job and job.status in ('succeeded','failed','cancelled'):
                r.status=job.status;r.result={**(r.result or {}),'status':job.status,
                    'content':'任务已完成，请在对应面板或任务中心核对结果。' if job.status=='succeeded' else (job.error or '任务已取消'),
                    'data':{'job_id':job.id,'job_result':job.result}};r.error=job.error
                await event(db,r,'run.status',{'status':r.status,'result':r.result})
        await db.commit()
    if rid:
        try:await execute_run(rid)
        except asyncio.CancelledError:
            await finish(rid,'failed',error='服务重启中断本轮；请核对产物与用量，不会自动重复生成。')
            raise
    return bool(rid)


async def queue_loop():
    """Separate consumer from chapter jobs: a long manuscript task never blocks all chat."""
    while True:
        try:
            if not await poll_once():await asyncio.sleep(2)
        except asyncio.CancelledError:raise
        except Exception:
            logging.getLogger(__name__).exception('Agent queue failed')
            await asyncio.sleep(3)
