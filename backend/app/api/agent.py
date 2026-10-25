"""Agent Run HTTP adapter. Execution occurs in the durable queue, not the browser connection."""
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
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

from ..services.agent_decisions import owned
from ..services.story_ports.agent import BackendStoryPorts
from storyclaw.agent import StoryClaw

def facade(rid,u):return StoryClaw(BackendStoryPorts(rid,u.id,None))

@router.post('/runs')
async def create(request:AgentRequest,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await service.create(request,u.id,db)

@router.get('/runs')
async def list_runs(book_id:int|None=None,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    q=select(AgentRun).where(AgentRun.user_id==u.id)
    if book_id is not None:q=q.where(AgentRun.request['scope']['book_id'].as_integer()==book_id)
    rows=await db.scalars(q.order_by(AgentRun.created_at.desc()).limit(100))
    return [service.out(r) for r in rows]

@router.get('/runs/{rid}')
async def status(rid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await facade(rid,u).status(rid)

@router.get('/runs/{rid}/events')
async def events(rid:str,after_seq:int=Query(0,ge=0),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await facade(rid,u).events(rid,after_seq)

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    decision_id:str
    accept:bool

@router.post('/runs/{rid}/decisions')
async def decide(rid:str,data:Decision,u:User=Depends(get_current_user)):
    return await facade(rid,u).resume(rid,data.model_dump())

@router.post('/runs/{rid}/cancel')
async def cancel(rid:str,u:User=Depends(get_current_user)):
    return await facade(rid,u).cancel(rid)

class AdoptCandidate(BaseModel):
    expected_hash:str=Field(min_length=64,max_length=64)

@router.post('/runs/{rid}/adopt')
async def adopt_candidate(rid:str,data:AdoptCandidate,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from ..services.agent_decisions import owned
    from ..models import Chapter,Book
    from ..services.revisions import assert_editable,chapter_hash,snapshot
    from storyclaw.continuity import prose
    from ..services.content import reading_html
    from sqlalchemy import select
    row=await owned(rid,u,db,True);result=row.result or {};artifact=result.get('data') or {}
    if row.status!='succeeded' or not artifact.get('artifact') or artifact.get('adopted'):raise HTTPException(409,'候选不可采用或已经采用')
    kind=artifact.get('kind','')
    if not kind.startswith('text.'):raise HTTPException(422,'此候选请在对应资料编辑页手动选择采用')
    cid=artifact.get('chapter_id');chapter=await db.get(Chapter,cid) if cid else None
    if not chapter:raise HTTPException(404,'章节不存在')
    book=await db.scalar(select(Book).where(Book.id==chapter.book_id,Book.user_id==u.id).with_for_update())
    if not book:raise HTTPException(404,'章节不存在')
    await db.refresh(chapter);await assert_editable(db,cid)
    if chapter_hash(chapter)!=data.expected_hash or artifact.get('base_hash')!=data.expected_hash:raise HTTPException(409,'正文已修改，请重新生成或手动对照采用')
    old=prose(chapter.content);candidate=result.get('content','').strip();selected=artifact.get('selected_text','')
    if not candidate:raise HTTPException(422,'候选正文为空')
    if kind=='text.continue':new=old+'\n\n'+candidate
    else:
        if not selected or old.count(selected)!=1:raise HTTPException(409,'原片段不存在或有重复，请在编辑器中手动采用')
        new=old.replace(selected,candidate,1)
    await snapshot(db,chapter,'agent-candidate');chapter.content=reading_html(new);chapter.word_count=len(''.join(new.split()));chapter.rag_status='pending'
    row.result={**result,'data':{**artifact,'adopted':True,'adopted_hash':chapter_hash(chapter)}}
    await db.commit();return {'chapter_id':cid,'content_hash':chapter_hash(chapter),'adopted':True}
