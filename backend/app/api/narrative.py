"""Author review of evidence, aliases, time ranges, causal links and character knowledge."""
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select
from ..database import get_db
from ..core.deps import get_current_user
from ..models import User,Chapter
from ..models.operations import NarrativeFact,NarrativeEntity,NarrativeFocus
from ..models.studio import IndexManifest
from ..services.library import own_book
from ..services.serial import assert_book_idle
from ..services.revisions import chapter_hash
from ..services.narrative_state import bump,out,view
router=APIRouter(tags=['narrative-state'])
class EntityIn(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    aliases:list[str]=Field(default_factory=list,max_length=20)
@router.get('/books/{bid}/narrative/entities')
async def entities(bid:int,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid)
    return [{'id':r.id,'name':r.name,'aliases':r.aliases} for r in await db.scalars(select(NarrativeEntity).where(NarrativeEntity.book_id==bid))]
@router.post('/books/{bid}/narrative/entities')
async def add_entity(bid:int,data:EntityIn,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid,True);await assert_book_idle(db,bid)
    from storyclaw.knowledge import alias_map
    existing=[{'name':r.name,'aliases':r.aliases} for r in await db.scalars(select(NarrativeEntity).where(NarrativeEntity.book_id==bid))]
    if any(r['name']==data.name for r in existing):raise HTTPException(409,'标准名已存在，请编辑已有映射')
    try:alias_map([*existing,data.model_dump()])
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    row=NarrativeEntity(id=str(uuid4()),book_id=bid,name=data.name,aliases=data.aliases);db.add(row);await bump(db,bid);await db.commit();return {'id':row.id}
@router.put('/books/{bid}/narrative/entities/{eid}')
async def edit_entity(bid:int,eid:str,data:EntityIn,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid,True);await assert_book_idle(db,bid)
    row=await db.get(NarrativeEntity,eid)
    if not row or row.book_id!=bid:raise HTTPException(404,'映射不存在')
    from storyclaw.knowledge import alias_map
    others=[{'name':r.name,'aliases':r.aliases} for r in await db.scalars(select(NarrativeEntity).where(NarrativeEntity.book_id==bid,NarrativeEntity.id!=eid))]
    if any(r['name']==data.name for r in others):raise HTTPException(409,'标准名已存在')
    try:alias_map([*others,data.model_dump()])
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    row.name=data.name;row.aliases=data.aliases;await bump(db,bid);await db.commit();return {'id':row.id}
@router.get('/books/{bid}/narrative/facts')
async def facts(bid:int,offset:int=Query(0,ge=0),u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid)
    rows=await db.scalars(select(NarrativeFact).where(NarrativeFact.book_id==bid).order_by(NarrativeFact.valid_from.desc(),NarrativeFact.id).offset(offset).limit(50))
    result=[]
    for r in rows:
        manifest=await db.get(IndexManifest,r.manifest_id) if r.manifest_id else None
        result.append({**out(r),'active':bool(manifest and manifest.status=='active')})
    return result
@router.get('/books/{bid}/narrative/view')
async def knowledge(bid:int,before:int=Query(1,ge=1),persona:str=Query('',max_length=120),u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid);return await view(db,bid,before,persona)
class FactIn(BaseModel):
    subject:str=Field(min_length=1,max_length=120)
    statement:str=Field(min_length=2,max_length=2000)
    quote:str=Field(min_length=2,max_length=1000)
    kind:Literal['event','state','belief','rule','promise']='state'
    certainty:Literal['observed','claim','inference']='claim'
    holder:str=Field(default='',max_length=120)
    known_by:list[str]=Field(default_factory=list,max_length=30)
    public:bool=False
    story_time:str=Field(default='',max_length=200)
    causes:list[str]=Field(default_factory=list,max_length=20)
    valid_until:int|None=Field(default=None,ge=1)
    review_status:Literal['suggested','confirmed','rejected']='confirmed'
class NewFact(FactIn):
    chapter_id:int
    expected_hash:str=Field(min_length=64,max_length=64)
class EditFact(FactIn):
    version:int=Field(ge=1)
async def validate_fact(db,bid,fid,data,chapter):
    from storyclaw.continuity import prose
    from storyclaw.knowledge import validate_causes
    if data.quote not in prose(chapter.content):raise HTTPException(422,'证据必须是该章原文中连续存在的片段')
    if data.kind=='belief' and not data.holder:raise HTTPException(422,'角色信念需要指定持有者')
    if data.valid_until is not None and data.valid_until<chapter.number:raise HTTPException(422,'有效期不能早于来源章')
    rows=list(await db.scalars(select(NarrativeFact).where(NarrativeFact.book_id==bid)))
    try:validate_causes(fid,data.causes,[{'id':r.id,'causes':r.causes} for r in rows])
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    if any(r.id in data.causes and r.valid_from>chapter.number for r in rows):raise HTTPException(422,'原因不能来自来源章之后的未来事实')
@router.post('/books/{bid}/narrative/facts')
async def new_fact(bid:int,data:NewFact,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid,True);await assert_book_idle(db,bid)
    chapter=await db.get(Chapter,data.chapter_id)
    if not chapter or chapter.book_id!=bid:raise HTTPException(404,'来源章节不存在')
    if data.expected_hash!=chapter_hash(chapter):raise HTTPException(409,'来源正文已变化')
    manifest=await db.scalar(select(IndexManifest).where(IndexManifest.chapter_id==chapter.id,IndexManifest.body_hash==data.expected_hash,IndexManifest.status=='active'))
    if not manifest or chapter.rag_status!='loaded':raise HTTPException(409,'请先审阅入库当前版本，再登记证据')
    fid=str(uuid4());await validate_fact(db,bid,fid,data,chapter)
    row=NarrativeFact(id=fid,book_id=bid,chapter_id=chapter.id,manifest_id=manifest.id,body_hash=data.expected_hash,valid_from=chapter.number,**data.model_dump(exclude={'chapter_id','expected_hash'}));db.add(row)
    await bump(db,bid);await db.commit();return out(row)
@router.put('/books/{bid}/narrative/facts/{fid}')
async def edit_fact(bid:int,fid:str,data:EditFact,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid,True);await assert_book_idle(db,bid)
    row=await db.get(NarrativeFact,fid)
    if not row or row.book_id!=bid:raise HTTPException(404,'事实记录不存在')
    if row.version!=data.version:raise HTTPException(409,'记录已被修改，请刷新后核对')
    chapter=await db.get(Chapter,row.chapter_id)
    if chapter_hash(chapter)!=row.body_hash:raise HTTPException(409,'原文版本已失效，请先重新入库')
    await validate_fact(db,bid,fid,data,chapter)
    for key,value in data.model_dump(exclude={'version'}).items():setattr(row,key,value)
    row.version+=1;await bump(db,bid);await db.commit();return out(row)
class FocusIn(BaseModel):
    persona:str=Field(default='',max_length=120)
@router.put('/books/{bid}/narrative/focus/{cid}')
async def focus(bid:int,cid:int,data:FocusIn,u:User=Depends(get_current_user),db=Depends(get_db)):
    await own_book(db,u.id,bid,True);await assert_book_idle(db,bid)
    c=await db.get(Chapter,cid)
    if not c or c.book_id!=bid:raise HTTPException(404,'章节不存在')
    row=await db.get(NarrativeFocus,cid)
    if not row:row=NarrativeFocus(chapter_id=cid,persona=data.persona);db.add(row)
    else:row.persona=data.persona
    await db.commit();return {'persona':row.persona}
