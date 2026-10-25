import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import get_current_user
from ..database import get_db
from ..models import Book, Chapter, User, Volume
from ..services.revisions import snapshot, chapter_hash, assert_editable
from ..schemas import ChapterCreateIn, ChapterDetailOut, ChapterOut, ChapterUpdateIn

router = APIRouter(prefix="/chapters", tags=["chapters"])


def _count_words(text: str) -> int:
    if not text:
        return 0
    text = re.sub(r"<[^>]+>", "", text)  # 去 HTML 标签
    return len(re.sub(r"\s+", "", text))


async def _check_book(bid: int, u: User, db: AsyncSession) -> Book:
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    return b


async def _own_chapter(cid: int, u: User, db: AsyncSession) -> Chapter:
    c = await db.get(Chapter, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    b = await db.get(Book, c.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "章节不存在")
    return c


@router.get("/books/{bid}", response_model=list[ChapterOut])
async def list_chapters(bid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _check_book(bid, u, db)
    rs = await db.scalars(select(Chapter).where(Chapter.book_id == bid).order_by(Chapter.number))
    return [ChapterOut.model_validate(c) for c in rs]


@router.post("/books/{bid}", response_model=ChapterDetailOut)
async def create_chapter(bid: int, data: ChapterCreateIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _check_book(bid, u, db)
    max_num = await db.scalar(select(func.max(Chapter.number)).where(Chapter.book_id == bid)) or 0
    if data.volume_id:
        v = await db.get(Volume, data.volume_id)
        if not v or v.book_id != bid:
            raise HTTPException(400, "卷不存在")
    c = Chapter(book_id=bid, volume_id=data.volume_id, number=max_num + 1,
                title=data.title, content="", word_count=0)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return ChapterDetailOut.model_validate(c)


@router.get("/{cid}", response_model=ChapterDetailOut)
async def get_chapter(cid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await _own_chapter(cid, u, db)
    return ChapterDetailOut.model_validate(c)


@router.put("/{cid}", response_model=ChapterDetailOut)
async def update_chapter(cid: int, data: ChapterUpdateIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await _own_chapter(cid, u, db)
    # Serialize manual saves and reject stale browser copies.
    book=await db.get(Book,c.book_id);await db.refresh(book,with_for_update=True)
    await db.refresh(c, with_for_update=True)
    await assert_editable(db, cid)
    if data.expected_hash and data.expected_hash != chapter_hash(c):
        raise HTTPException(409, '正文已被其他窗口或任务修改，请刷新后核对再保存')
    if (data.content is not None and data.content != c.content) or (data.title is not None and data.title != c.title):
        await snapshot(db, c, 'manual')
    if data.title is not None:
        if c.title!=data.title:c.rag_status='pending'
        c.title = data.title
    if data.volume_id is not None:
        c.volume_id = data.volume_id
    if data.content is not None:
        if c.content != data.content:
            c.rag_status = "pending"
        c.content = data.content
        c.word_count = _count_words(data.content)
    await db.commit()
    await db.refresh(c)
    return ChapterDetailOut.model_validate(c)


@router.delete("/{cid}")
async def delete_chapter(cid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await _own_chapter(cid, u, db)
    await assert_editable(db, cid)
    from ..services.serial import invalidate_following
    await invalidate_following(db,c,f'第{c.number}章已删除，请复核后文')
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.get('/{cid}/revisions')
async def list_revisions(cid: int, u: User=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    from ..models.product import ChapterRevision
    await _own_chapter(cid,u,db)
    rows=await db.scalars(select(ChapterRevision).where(ChapterRevision.chapter_id==cid).order_by(ChapterRevision.id.desc()).limit(100))
    return [{'id':r.id,'title':r.title,'word_count':r.word_count,'source':r.source,'created_at':str(r.created_at)} for r in rows]

@router.get('/{cid}/revisions/{rid}')
async def get_revision(cid:int,rid:int,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from ..models.product import ChapterRevision
    await _own_chapter(cid,u,db)
    r=await db.get(ChapterRevision,rid)
    if not r or r.chapter_id!=cid:raise HTTPException(404,'版本不存在')
    return {'id':r.id,'title':r.title,'content':r.content,'word_count':r.word_count,'content_hash':r.content_hash}

@router.post('/{cid}/revisions/{rid}/restore',response_model=ChapterDetailOut)
async def restore_revision(cid:int,rid:int,data:ChapterUpdateIn,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from ..models.product import ChapterRevision
    c=await _own_chapter(cid,u,db)
    book=await db.get(Book,c.book_id);await db.refresh(book,with_for_update=True)
    await db.refresh(c,with_for_update=True)
    await assert_editable(db,cid)
    if data.expected_hash and data.expected_hash!=chapter_hash(c):raise HTTPException(409,'正文已变更，请刷新版本列表')
    r=await db.get(ChapterRevision,rid)
    if not r or r.chapter_id!=cid:raise HTTPException(404,'版本不存在')
    await snapshot(db,c,'before_restore')
    c.title=r.title;c.content=r.content;c.word_count=r.word_count;c.rag_status='pending'
    await db.commit();await db.refresh(c)
    return ChapterDetailOut.model_validate(c)
