"""HTTP adapters for per-chapter author planning and continuity notices."""
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import ConfigEntity
from app.models import User
from app.services.writing import serial as svc
from storyclaw.workflows.serial import Blueprint
from storyclaw.workflows.serial import digest
router=APIRouter(tags=['serial-writing'])

async def owned(cid,u,db):
    chapter=await db.get(Chapter,cid)
    book=await db.get(Book,chapter.book_id) if chapter else None
    if not book or book.user_id!=u.id:raise HTTPException(404,'章节不存在')
    return chapter

@router.get('/chapters/{cid}/blueprint')
async def get_blueprint(cid:int,u:User=Depends(get_current_user),db=Depends(get_db)):
    return await svc.blueprint_state(db,await owned(cid,u,db))

@router.put('/chapters/{cid}/blueprint')
async def save_blueprint(cid:int,data:Blueprint,u:User=Depends(get_current_user),db=Depends(get_db)):
    chapter=await owned(cid,u,db)
    book=await db.get(Book,chapter.book_id);await db.refresh(book,with_for_update=True)
    await svc.assert_book_idle(db,chapter.book_id)
    stamp=(await svc.inputs(db,chapter))[3]
    await svc.save_blueprint(db,chapter,data.model_dump(),stamp)
    await db.commit()
    return await svc.blueprint_state(db,chapter)

@router.post('/chapters/{cid}/blueprint/confirm')
async def confirm_blueprint(cid:int,data:Blueprint,u:User=Depends(get_current_user),db=Depends(get_db)):
    chapter=await owned(cid,u,db)
    book=await db.get(Book,chapter.book_id);await db.refresh(book,with_for_update=True)
    await svc.assert_book_idle(db,chapter.book_id)
    state=await svc.blueprint_state(db,chapter)
    if state['stale'] or state['plan']!=data.model_dump():raise HTTPException(409,'章纲或参考资料已变化，请重新核对、保存后再确认')
    row=await svc.record(db,chapter)
    if not row:raise HTTPException(409,'请先保存本章章纲')
    previous=(row.extra_json or {}).get('confirmed_hash')
    row.extra_json={**row.extra_json,'confirmed_hash':digest(state['plan']),'confirmed_dependencies':state['dependencies']}
    if previous!=digest(state['plan']) and chapter.word_count>0:
        await svc.invalidate_following(db,chapter,f'第{chapter.number}章章纲已变更，请复核本章及后文',include_self=True)
    await db.commit()
    return await svc.blueprint_state(db,chapter)

@router.get('/books/{bid}/workflow')
async def workflow(bid:int,u:User=Depends(get_current_user),db=Depends(get_db)):
    book=await db.get(Book,bid)
    if not book or book.user_id!=u.id:raise HTTPException(404,'作品不存在')
    notices=list(await db.scalars(select(ConfigEntity).where(ConfigEntity.book_id==bid,ConfigEntity.entity_type=='workflow',ConfigEntity.category=='continuity-impact')))
    existing=set(await db.scalars(select(Chapter.id).where(Chapter.book_id==bid)))
    return {'book_id':bid,'impacts':[r.extra_json for r in notices if (r.extra_json or {}).get('active') and r.extra_json.get('chapter_id') in existing]}
