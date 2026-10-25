"""Agent Run HTTP adapter. Execution occurs in the durable queue, not the browser connection."""
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.contracts import AgentRequest
from ..core.deps import get_current_user
from ..database import get_db
from ..models import User,Chapter
from ..models.agent import AgentRun,AgentEvent
from ..models.product import WorkJob
from ..services import agent_runs as service

router=APIRouter(prefix='/agent',tags=['agent-runs'])

async def owned(rid,u,db,lock=False):
    q=select(AgentRun).where(AgentRun.id==rid,AgentRun.user_id==u.id)
    row=await db.scalar(q.with_for_update() if lock else q)
    if not row:raise HTTPException(404,'请求不存在')
    return row

@router.post('/runs')
async def create(request:AgentRequest,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await service.create(request,u.id,db)

@router.get('/runs')
async def list_runs(book_id:int|None=None,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    rows=list(await db.scalars(select(AgentRun).where(AgentRun.user_id==u.id).order_by(AgentRun.created_at.desc()).limit(100)))
    return [service.out(r) for r in rows if book_id is None or r.request.get('scope',{}).get('book_id')==book_id]

@router.get('/runs/{rid}')
async def status(rid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return service.out(await owned(rid,u,db))

@router.get('/runs/{rid}/events')
async def events(rid:str,after_seq:int=Query(0,ge=0),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await owned(rid,u,db)
    rows=await db.scalars(select(AgentEvent).where(AgentEvent.run_id==rid,AgentEvent.seq>after_seq).order_by(AgentEvent.seq).limit(200))
    return [{'id':e.id,'run_id':e.run_id,'seq':e.seq,'type':e.type,'payload':e.payload} for e in rows]

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    decision_id:str
    accept:bool

@router.post('/runs/{rid}/decisions')
async def decide(rid:str,data:Decision,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    row=await owned(rid,u,db,True)
    decision=row.decision or {}
    if data.decision_id!=decision.get('id'):raise HTTPException(409,'确认卡已失效')
    if row.status!='waiting_author':return service.out(row)
    if not data.accept:
        row.status='cancelled';await service.event(db,row,'run.status',{'status':'cancelled'});await db.commit();return service.out(row)
    request=AgentRequest.model_validate(row.request)
    await service.validate_scope(db,u.id,request.scope)
    chapter=await db.get(Chapter,request.scope.chapter_id)
    from ..services.revisions import chapter_hash
    if not chapter or chapter_hash(chapter)!=decision['content_hash']:raise HTTPException(409,'正文已改变，请核对新稿后重新请求')
    from ..services.work_commands import create_job,JobInput
    from storyclaw.orchestration.capabilities import get_capability
    from uuid import uuid5,NAMESPACE_URL
    cap=get_capability(decision['command'])
    body={'request_id':str(uuid5(NAMESPACE_URL,row.id+':'+cap.name)),
          'book_id':request.scope.book_id,'chapter_id':chapter.id,'kind':cap.job_kind,**decision['payload']}
    result=await create_job(JobInput.model_validate(body),u,db)
    # create_job commits its idempotent operation; linking is repeatable after a crash.
    row.status='waiting_task';row.job_id=result['id'];row.result={'status':'waiting_task','content':'已确认并提交任务','data':{'job_id':result['id']}}
    await service.event(db,row,'run.status',{'status':'waiting_task','result':row.result});await db.commit();return service.out(row)

@router.post('/runs/{rid}/cancel')
async def cancel(rid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    row=await owned(rid,u,db,True)
    if row.status in service.TERMINAL:return service.out(row)
    if row.job_id:
        job=await db.scalar(select(WorkJob).where(WorkJob.id==row.job_id,WorkJob.user_id==u.id).with_for_update())
        if job and job.status=='running':raise HTTPException(409,'后台任务已执行，请等待当前步骤结束；不会自动启动下一步')
        if job and job.status=='queued':job.status='cancelled';job.finished_at=service.now()
    row.status='cancelled';await service.event(db,row,'run.status',{'status':'cancelled'});await db.commit();return service.out(row)
