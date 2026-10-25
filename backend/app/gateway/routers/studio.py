"""Durable long-form plans and author-controlled checkpoints."""
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.models.studio import StudioTask
from app.models.studio import SourceChapter
from app.services.library.library import own_book
from app.services.library.library import own_source
from app.services.jobs.studio_tasks import create_task
from app.services.jobs.studio_tasks import task_out
router=APIRouter(tags=['studio'])
class PlanIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:str=Field(default_factory=lambda:str(uuid4()),max_length=64)
    kind:Literal['serial','source-analysis']
    start:int=Field(default=1,ge=1,le=10000)
    end:int=Field(default=3,ge=1,le=10000)
    budget:int=Field(ge=1,le=1000000)
    auto_adopt:bool=False
    instruction:str=Field(default='',max_length=6000)
    source_id:str|None=None
@router.post('/books/{bid}/plans')
async def create(bid:int,data:PlanIn,u:User=Depends(get_current_user),db=Depends(get_db)):
    if data.end<data.start or (data.kind=='serial' and data.end-data.start>100):raise HTTPException(422,'每次连续写作最多101章，请分阶段确认')
    if data.kind=='source-analysis' and not data.source_id:raise HTTPException(422,'请选择来源')
    return task_out(await create_task(db,u.id,bid,data.kind,data.request_id,data.model_dump(exclude={'kind','request_id','budget'}),data.budget))
@router.get('/books/{bid}/plans')
async def plans(bid:int,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid)
    return [task_out(t) for t in await db.scalars(select(StudioTask).where(StudioTask.book_id==bid).order_by(StudioTask.created_at.desc()).limit(50))]
class Control(BaseModel):
    action:Literal['pause','resume','cancel']
    budget:int|None=Field(default=None,ge=1,le=1000000)
@router.post('/plans/{tid}/control')
async def control(tid:str,data:Control,u:User=Depends(get_current_user),db=Depends(get_db)):
    t=await db.scalar(select(StudioTask).where(StudioTask.id==tid,StudioTask.user_id==u.id).with_for_update())
    if not t:raise HTTPException(404,'计划不存在')
    if t.status in ('succeeded','cancelled'):raise HTTPException(409,'计划已结束')
    if data.budget is not None:
        if data.budget<t.spent:raise HTTPException(422,'预算不能低于已用积分')
        t.budget=data.budget
    if data.action=='resume':
        if t.status in ('running','queued'):return task_out(t)
        other=await db.scalar(select(StudioTask.id).where(StudioTask.book_id==t.book_id,StudioTask.id!=tid,StudioTask.status.in_(['running','queued'])))
        if other:raise HTTPException(409,'本书已有运行计划')
        if t.current_job:
            from app.models.product import WorkJob
            job=await db.get(WorkJob,t.current_job)
            if job and job.status in ('failed','cancelled'):
                t.current_job=None;t.result={**t.result,'attempt':t.result.get('attempt',0)+1}
        t.status='queued';t.error=None;t.lease_until=None
    else:
        t.status='cancelled' if data.action=='cancel' else 'paused'
        # Running inference is allowed to finish; no new call can reserve against this plan.
        if t.current_job:
            from app.models.product import WorkJob
            job=await db.get(WorkJob,t.current_job)
            if job and job.status=='queued':job.status='cancelled';job.error='所属计划已暂停';t.current_job=None;t.result={**t.result,'attempt':t.result.get('attempt',0)+1}
    await db.commit();return task_out(t)
@router.post('/sources/{sid}/chapters/{number}/retry')
async def retry(sid:str,number:int,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_source(db,u.id,sid)
    active=await db.scalar(select(StudioTask.id).where(StudioTask.user_id==u.id,StudioTask.kind=='source-analysis',StudioTask.status.in_(['queued','running'])))
    if active:raise HTTPException(409,'请先暂停来源分析计划')
    row=await db.scalar(select(SourceChapter).where(SourceChapter.source_id==sid,SourceChapter.number==number))
    if not row:raise HTTPException(404,'来源章节不存在')
    row.analysis_status='pending';row.error=None;await db.commit();return {'status':'pending'}
@router.get('/sources/{sid}/chapters/{number}')
async def read(sid:str,number:int,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_source(db,u.id,sid)
    row=await db.scalar(select(SourceChapter).where(SourceChapter.source_id==sid,SourceChapter.number==number))
    if not row:raise HTTPException(404,'来源章节不存在')
    return {'title':row.title,'content':row.content,'hash':row.content_hash,'analysis':row.analysis}
