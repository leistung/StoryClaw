"""Shared job submission policy for HTTP buttons and StoryClaw tools."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel,Field
from fastapi import HTTPException
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Book,Chapter,User
from ..models.product import WorkJob
from .revisions import chapter_hash

class JobInput(BaseModel):
    planning_mode:Literal['serial','fixed']='serial'
    design_type:Literal['character','world','plot']='character'
    reviewed_hash:str=''
    book_id:int
    chapter_id:int|None=None
    kind:Literal['generate','revise','scene-plan','index','analysis','outline','story-design','chapter-outline']
    request_id:str=Field(min_length=16,max_length=64,pattern=r'^[A-Za-z0-9-]+$')
    prompt:str=Field(default='',max_length=12000)
    skill:Literal['book-summary','consistency-check','character-development','plot-planning']='book-summary'
    start:int=Field(default=1,ge=1)
    end:int=Field(default=10,ge=1)

def job_out(job):
    return {key:(getattr(job,key).isoformat() if isinstance(getattr(job,key),datetime) else getattr(job,key)) for key in ('id','book_id','chapter_id','kind','status','result','error','created_at','started_at','finished_at')}

async def create_job(data:JobInput,u:User,db:AsyncSession,*,plan_id=None):
    await db.execute(text("SELECT pg_advisory_xact_lock(CAST(:key AS BIGINT))"), {"key":0x53434C000000 + u.id})
    b=await db.scalar(select(Book).where(Book.id==data.book_id,Book.user_id==u.id).with_for_update())
    if not b:raise HTTPException(404,'作品不存在')
    prior=await db.scalar(select(WorkJob).where(WorkJob.user_id==u.id,WorkJob.request_id==data.request_id))
    payload=data.model_dump(exclude={'request_id'})
    if prior:
        if prior.payload.get('studio_plan')!=plan_id:raise HTTPException(409,'请求已用于其他计划范围')
        original={k:v for k,v in prior.payload.items() if k not in ('base_hash','outline_hash','method_snapshot','studio_plan')}
        for key in ('design_type','reviewed_hash','planning_mode'):original.setdefault(key,JobInput.model_fields[key].default)
        if original!=payload:raise HTTPException(409,'请求编号已用于不同任务')
        return job_out(prior)
    from ..services.planning import require_outline
    planning=await db.scalar(select(WorkJob.id).where(WorkJob.book_id==b.id,WorkJob.status.in_(['queued','running']),WorkJob.kind=='outline'))
    if planning:raise HTTPException(409,'本书大纲正在生成，请到任务中心查看进度')
    if data.kind=='outline':
        active_book=await db.scalar(select(WorkJob.id).where(WorkJob.book_id==b.id,WorkJob.status.in_(['queued','running'])))
        if active_book:raise HTTPException(409,'请先完成或取消本书现有任务，再重新生成大纲')
    if data.kind in ('generate','revise','scene-plan','story-design','chapter-outline') or (data.kind=='analysis' and data.skill=='plot-planning'):
        payload['outline_hash']=await require_outline(db,b.id)
    if data.kind not in ('analysis','outline','story-design'):
        c=await db.scalar(select(Chapter).where(Chapter.id==data.chapter_id,Chapter.book_id==b.id).with_for_update())
        if not c:raise HTTPException(404,'章节不存在')
        if data.kind in ('generate','revise','scene-plan'):
            from ..services.serial import require_blueprint
            await require_blueprint(db,c)
        if data.kind in ('generate','revise','chapter-outline','scene-plan'):
            from ..services.planning import require_previous_memory
            await require_previous_memory(db,c)
        if data.kind=='revise' and not c.content:raise HTTPException(400,'当前章节没有可修改的正文')
        if data.kind=='index' and not c.content:raise HTTPException(400,'请先写入正文')
        if data.kind=='index' and data.reviewed_hash!=chapter_hash(c):raise HTTPException(409,'请核对并确认当前正文后再更新记忆；正文已变化时需要重新确认')
        busy=await db.scalar(select(WorkJob.id).where(WorkJob.chapter_id==c.id,WorkJob.status.in_(['queued','running'])))
        if busy:raise HTTPException(409,'该章节已有任务，请在任务中心查看')
        payload['base_hash']=chapter_hash(c)
    same_book=await db.scalar(select(WorkJob.id).where(WorkJob.book_id==b.id,WorkJob.status.in_(['queued','running'])))
    if same_book:raise HTTPException(409,'本书已有任务，请完成或取消后再发起下一步，避免使用未完成的上下文')
    if data.kind=='analysis' and data.end<data.start:raise HTTPException(400,'章节范围无效')
    active=list(await db.scalars(select(WorkJob.id).where(WorkJob.user_id==u.id,WorkJob.status.in_(['queued','running']))))
    if len(active)>=3:raise HTTPException(429,'最多同时保留三个待执行任务')
    if data.kind in ('generate','revise','scene-plan','analysis','outline','story-design','chapter-outline') and u.credits_balance<1:raise HTTPException(402,'积分不足')
    from storyclaw.skills import describe_skill
    methods={'outline':['framework-design'],'chapter-outline':['plot-design'],
        'generate':['chapter-craft','continuity-review'],'revise':['chapter-craft','continuity-review'],
        'scene-plan':['plot-design'],'story-design':[{'world':'world-design','character':'character-arc','plot':'plot-design'}[data.design_type]],
        'analysis':[{'book-summary':'story-summarization','consistency-check':'continuity-review','character-development':'character-arc','plot-planning':'plot-design'}[data.skill]],'index':[]}[data.kind]
    payload['method_snapshot']=[{key:meta[key] for key in ('name','version','content_hash')} for meta in map(describe_skill,methods) if meta.get('available')]
    job=WorkJob(id=str(uuid4()),user_id=u.id,book_id=b.id,chapter_id=data.chapter_id if data.kind not in ('analysis','outline','story-design') else None,kind=data.kind,request_id=data.request_id,payload=payload)
    if plan_id:
        from ..models.studio import StudioTask
        plan=await db.get(StudioTask,plan_id)
        if not plan or plan.user_id!=u.id or plan.book_id!=b.id:raise HTTPException(403,'计划范围不匹配')
        job.payload={**job.payload,'studio_plan':plan.id};plan.current_job=job.id
    db.add(job);await db.commit();await db.refresh(job)
    return job_out(job)

