from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..core.deps import get_current_user
from ..models import Book,Chapter,User
from ..models.product import WorkJob
from ..services.revisions import chapter_hash

router=APIRouter(tags=['work-jobs'])
from ..services.work_commands import JobInput, job_out, create_job as submit_job

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
    from ..models import ConfigEntity
    from ..services.planning import require_outline
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
        from ..services.serial import invalidate_book
        await invalidate_book(db,j.book_id,'已采用新的作者设定，请复核既有正文')
    j.result=result;await db.commit()
    return result
