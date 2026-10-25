"""Source upload, provenance, takeover and derivative branch commands."""
import json
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form,Query
from fastapi.responses import Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.models.studio import StorySource
from app.models.studio import SourceChapter
from app.models.studio import ProjectBaseline
from app.services.library import library as svc
router=APIRouter(tags=['story-library'])

@router.post('/books/{bid}/sources')
async def upload(bid:int,file:UploadFile=File(...),basis:Literal['own','licensed','public_domain','unknown']=Form('own'),ai_allowed:bool=Form(False),commercial_allowed:bool=Form(False),read_allowed:bool=Form(False),license_note:str=Form(''),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from storyclaw.workflows.library import MAX_FILE
    data=await file.read(MAX_FILE+1)
    if len(data)>MAX_FILE:raise HTTPException(413,'单文件最多24MB')
    row=await svc.upload(db,u.id,bid,file.filename or 'manuscript.txt',data,{'basis':basis,'read_allowed':read_allowed,'ai_allowed':ai_allowed,'commercial_allowed':commercial_allowed,'note':license_note[:4000]})
    return await svc.coverage(db,row)

@router.get('/books/{bid}/sources')
async def sources(bid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await svc.own_book(db,u.id,bid)
    rows=list(await db.scalars(select(StorySource).where(StorySource.user_id==u.id,StorySource.book_id==bid).order_by(StorySource.created_at.desc())))
    return [await svc.coverage(db,r) for r in rows]

@router.get('/sources/{sid}/chapters')
async def chapters(sid:str,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await svc.own_source(db,u.id,sid)
    rows=await db.scalars(select(SourceChapter).where(SourceChapter.source_id==sid).order_by(SourceChapter.number).offset(offset).limit(limit))
    return [{'id':r.id,'number':r.number,'title':r.title,'words':r.words,'hash':r.content_hash,'analysis_status':r.analysis_status,'error':r.error,'analysis':r.analysis} for r in rows]

@router.get('/sources/{sid}/original')
async def original(sid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    row=await svc.own_source(db,u.id,sid)
    from app.services.storage.blob_store import read_original
    return Response(await read_original(db,row),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="manuscript-original"'})

@router.post('/sources/{sid}/revoke')
async def revoke(sid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    row=await svc.own_source(db,u.id,sid);row.status='revoked'
    baselines=list(await db.scalars(select(ProjectBaseline).where(ProjectBaseline.source_id==sid)))
    from app.services.writing.serial import invalidate_book
    for b in baselines:
        b.status='stale';b.version+=1;await invalidate_book(db,b.book_id,'参考来源已撤销，请核对派生内容')
    from app.models.studio import StudioTask
    from sqlalchemy import or_
    tasks=list(await db.scalars(select(StudioTask).where(StudioTask.user_id==u.id,StudioTask.status.in_(['queued','running']),or_(StudioTask.book_id.in_([b.book_id for b in baselines]),StudioTask.payload['source_id'].as_string()==sid))))
    for task in tasks:task.status='paused';task.error='来源已停用，新的模型调用已停止'
    await db.commit();return {'status':'revoked','affected_books':[b.book_id for b in baselines]}

class BaselineIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_id:str
    file_hash:str=Field(min_length=64,max_length=64)
    mode:Literal['takeover','derivative']
    cutoff:int=Field(ge=1)
    notes:str=Field(min_length=20,max_length=12000)
    overrides:str=Field(default='',max_length=12000)
    branch_kind:Literal['continuation','if','au','original_character']='continuation'
    additional_words:int=Field(default=3000000,ge=1000,le=10000000)

def baseline_out(row):return {k:getattr(row,k) for k in ('book_id','source_id','mode','status','cutoff','notes','overrides','branch_kind','version','confirmed_hash')}

@router.get('/books/{bid}/baseline')
async def baseline(bid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await svc.own_book(db,u.id,bid);row=await db.get(ProjectBaseline,bid)
    return baseline_out(row) if row else None

@router.post('/books/{bid}/baseline/confirm')
async def confirm(bid:int,data:BaselineIn,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from app.services.writing.serial import assert_book_idle
    await svc.own_book(db,u.id,bid);await assert_book_idle(db,bid)
    return baseline_out(await svc.baseline_confirm(db,u.id,bid,data.model_dump()))

@router.get('/sources/{sid}')
async def source_detail(sid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await svc.coverage(db,await svc.own_source(db,u.id,sid))

@router.get('/sources')
async def all_sources(offset:int=Query(0,ge=0),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    rows=list(await db.scalars(select(StorySource).where(StorySource.user_id==u.id).order_by(StorySource.created_at.desc()).offset(offset).limit(50)))
    return [await svc.coverage(db,r) for r in rows]
