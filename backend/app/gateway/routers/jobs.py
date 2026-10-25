from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user
from app.models import Book
from app.models import Chapter
from app.models import User
from app.models.product import WorkJob
from app.services.writing.revisions import chapter_hash

router=APIRouter(tags=['work-jobs'])
from app.services.agent.work_commands import JobInput
from app.services.agent.work_commands import job_out
from app.services.agent.work_commands import create_job as submit_job

@router.post('/jobs')
async def create_job(data:JobInput,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await submit_job(data,u,db)

@router.get('/jobs')
async def list_jobs(book_id:int|None=None,limit:int=Query(30,ge=1,le=100),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    q=select(WorkJob).where(WorkJob.user_id==u.id)
    if book_id is not None:q=q.where(WorkJob.book_id==book_id)
    rows=await db.scalars(q.order_by(WorkJob.created_at.desc()).limit(limit))
    return [job_out(j) for j in rows]

@router.get('/jobs/{jid}')
async def get_job(jid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    j=await db.get(WorkJob,jid)
    if not j or j.user_id!=u.id:raise HTTPException(404,'任务不存在')
    return job_out(j)

@router.post('/jobs/{jid}/cancel')
async def cancel_job(jid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    j=await db.scalar(select(WorkJob).where(WorkJob.id==jid,WorkJob.user_id==u.id).with_for_update())
    if not j:raise HTTPException(404,'任务不存在')
    if j.status!='queued':raise HTTPException(409,'只有排队中的任务可以取消')
    j.status='cancelled';j.finished_at=datetime.now(timezone.utc);await db.commit()
    return job_out(j)


@router.post('/jobs/{jid}/adopt')
async def adopt_design(jid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from app.models import ConfigEntity
    from app.services.writing.planning import require_outline
    j=await db.scalar(select(WorkJob).where(WorkJob.id==jid,WorkJob.user_id==u.id).with_for_update())
    if not j:raise HTTPException(404,'任务不存在')
    if j.kind!='story-design' or j.status!='succeeded':raise HTTPException(409,'此任务没有可采用的设计草案')
    result=dict(j.result)
    if result.get('applied'):return result
    book=await db.scalar(select(Book).where(Book.id==j.book_id,Book.user_id==u.id).with_for_update())
    if not book:raise HTTPException(404,'作品不存在')
    if await require_outline(db,j.book_id)!=j.payload.get('outline_hash'):raise HTTPException(409,'大纲已变更，请核对后重新生成设计草案')
    active=await db.scalar(select(WorkJob.id).where(WorkJob.book_id==j.book_id,WorkJob.status.in_(['queued','running'])))
    if active:raise HTTPException(409,'请等待本书任务完成后再采用设定')
    added=skipped=0
    for card in result['dossiers']:
        prior=await db.scalar(select(ConfigEntity.id).where(ConfigEntity.book_id==j.book_id,ConfigEntity.entity_type==result['design_type'],ConfigEntity.name==card['name']))
        if prior:skipped+=1;continue
        db.add(ConfigEntity(book_id=j.book_id,entity_type=result['design_type'],name=card['name'],category=card['category'],description=card['description'],extra_json={**card.get('extra',{}),'source_job':j.id}))
        await db.flush();added+=1
    result.update(applied=True,added=added,skipped=skipped)
    if added:
        from app.services.writing.serial import invalidate_book
        await invalidate_book(db,j.book_id,'已采用新的作者设定，请复核既有正文')
    j.result=result;await db.commit()
    return result

class CandidateAdoption(BaseModel):
    expected_hash:str=Field(min_length=64,max_length=64)
@router.post('/jobs/{jid}/candidate/adopt')
async def adopt_candidate(jid:str,data:CandidateAdoption,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from app.services.writing.generation_candidates import adopt
    return await adopt(db,u.id,jid,data.expected_hash)

@router.post('/jobs/{jid}/candidate/recover')
async def recover_candidate(jid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from app.models import Message
    from storyclaw.runtime.execution import recover_candidate as recover
    job=await db.scalar(select(WorkJob).where(WorkJob.id==jid,WorkJob.user_id==u.id).with_for_update())
    if not job or job.kind not in ('generate','revise'):raise HTTPException(404,'生成任务不存在')
    if job.status!='failed':raise HTTPException(409,'只有已失败任务需要检查点恢复')
    if (job.result or {}).get('candidate'):return job_out(job)
    if not job.finished_at:raise HTTPException(409,'任务尚未结束')
    messages=list(await db.scalars(select(Message).where(Message.user_id==u.id,Message.role=='user',Message.content==job.payload.get('prompt',''),Message.created_at>=job.created_at,Message.created_at<=job.finished_at).order_by(Message.created_at.desc()).limit(10)))
    for message in messages:
        result=await recover(message.thread_id,u.id,job.book_id,job.chapter_id)
        if result:
            job.result={**(job.result or {}),'thread_id':message.thread_id,'candidate':{'content':result['content'],'chapter_id':job.chapter_id,'base_hash':job.payload['base_hash'],'adopted':False,'warning':'从本次任务时段的同范围检查点恢复；未经最终审阅，请核对后选择采用。'}}
            await db.commit();return job_out(job)
    raise HTTPException(404,'没有可恢复的同范围检查点候选，未调用模型')
