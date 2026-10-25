from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..core.deps import get_current_user
from ..models import Book,Chapter,User
from ..models.product import Publication
from ..models.platform import PlatformEvent
from ..services.content import reading_html
router=APIRouter(tags=['publications'])

async def own(db,bid,uid):
    b=await db.scalar(select(Book).where(Book.id==bid,Book.user_id==uid).with_for_update())
    if not b:raise HTTPException(404,'作品不存在')
    return b

@router.get('/books/{bid}/publication')
async def status(bid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await own(db,bid,u.id);p=await db.get(Publication,bid)
    return {'visible':bool(p and p.visible),'published_at':p.published_at.isoformat() if p else None,'chapter_count':len(p.snapshot.get('chapters',[])) if p else 0,'url':f'/read/{bid}'}

@router.post('/books/{bid}/publication')
async def publish(bid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    b=await own(db,bid,u.id)
    chapters=list(await db.scalars(select(Chapter).where(Chapter.book_id==bid,Chapter.word_count>0).order_by(Chapter.number)))
    if not chapters:raise HTTPException(400,'请先完成至少一章正文')
    snapshot={k:getattr(b,k) or '' for k in ('id','title','intro','genre','cover_url','protagonist_name','protagonist_intro')}
    snapshot['chapters']=[{'id':c.id,'number':c.number,'title':c.title,'word_count':c.word_count,'content':reading_html(c.content)} for c in chapters]
    p=await db.get(Publication,bid)
    if not p:p=Publication(book_id=bid,user_id=u.id,snapshot=snapshot);db.add(p)
    p.snapshot=snapshot;p.visible=True;p.published_at=datetime.now(timezone.utc)
    db.add(PlatformEvent(kind='audit',actor_id=u.id,action='book.publish',target=str(bid),details={'chapters':len(chapters)}))
    await db.commit()
    return {'visible':True,'chapter_count':len(chapters),'url':f'/read/{bid}'}

@router.post('/books/{bid}/publication/unpublish')
async def unpublish(bid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await own(db,bid,u.id);p=await db.get(Publication,bid)
    if p:p.visible=False
    db.add(PlatformEvent(kind='audit',actor_id=u.id,action='book.unpublish',target=str(bid),details={}))
    await db.commit();return {'visible':False}
