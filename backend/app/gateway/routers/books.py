import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import User
from app.models import Volume
from app.schemas import BookCreateIn
from app.schemas import BookOut
from app.schemas import BookUpdateIn
from app.schemas import StatsOut
from app.schemas import VolumeIn
from app.schemas import VolumeOut

router = APIRouter(prefix="/books", tags=["books"])


def _platforms_to_list(s: str | None) -> list[str]:
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


def _book_to_out(b: Book, chapter_count: int = 0, total_words: int = 0) -> BookOut:
    return BookOut(
        id=b.id, user_id=b.user_id, title=b.title, intro=b.intro, genre=b.genre,
        platforms=_platforms_to_list(b.platforms), cover_url=b.cover_url,
        target_chapters=b.target_chapters, target_words=b.target_words,
        per_chapter_words=b.per_chapter_words, protagonist_name=b.protagonist_name,
        protagonist_intro=b.protagonist_intro, chapter_count=chapter_count,
        total_words=total_words, created_at=b.created_at, updated_at=b.updated_at,
    )


async def _book_stats(db: AsyncSession, bid: int) -> tuple[int, int]:
    cc = await db.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == bid)) or 0
    tw = await db.scalar(select(func.coalesce(func.sum(Chapter.word_count), 0)).where(Chapter.book_id == bid)) or 0
    return int(cc), int(tw)


@router.get("/stats", response_model=StatsOut)
async def stats(u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = await db.scalar(select(func.coalesce(func.sum(Chapter.word_count), 0)).join(
        Book, Book.id == Chapter.book_id).where(
        Book.user_id == u.id, func.date(Chapter.updated_at) == func.current_date())) or 0
    month = await db.scalar(select(func.coalesce(func.sum(Chapter.word_count), 0)).join(
        Book, Book.id == Chapter.book_id).where(
        Book.user_id == u.id,
        func.date_trunc("month", Chapter.updated_at) == func.date_trunc("month", func.current_date()))) or 0
    total = await db.scalar(select(func.coalesce(func.sum(Chapter.word_count), 0)).join(
        Book, Book.id == Chapter.book_id).where(Book.user_id == u.id)) or 0
    return StatsOut(today_words=int(today), month_words=int(month), total_words=int(total))


@router.get("", response_model=list[BookOut])
async def list_books(u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    books = await db.scalars(select(Book).where(Book.user_id == u.id).order_by(Book.updated_at.desc()))
    out = []
    for b in books:
        cc, tw = await _book_stats(db, b.id)
        out.append(_book_to_out(b, cc, tw))
    return out


@router.post("", response_model=BookOut)
async def create_book(data: BookCreateIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.generate_outline or data.generate_plots or data.generate_characters:
        raise HTTPException(400,'请先创建作品，再在工作台逐步发起任务并确认大纲；开书时不再自动生成内容')
    b = Book(
        user_id=u.id, title=data.title, intro=data.intro, genre=data.genre,
        platforms=json.dumps(data.platforms, ensure_ascii=False), cover_url=data.cover_url,
        target_chapters=data.target_chapters, target_words=data.target_words,
        per_chapter_words=data.per_chapter_words, protagonist_name=data.protagonist_name,
        protagonist_intro=data.protagonist_intro,
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return _book_to_out(b)


@router.get("/{bid}", response_model=BookOut)
async def get_book(bid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    cc, tw = await _book_stats(db, bid)
    return _book_to_out(b, cc, tw)


@router.put("/{bid}", response_model=BookOut)
async def update_book(bid: int, data: BookUpdateIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        if k == "platforms":
            b.platforms = json.dumps(v, ensure_ascii=False)
        else:
            setattr(b, k, v)
    await db.commit()
    await db.refresh(b)
    return _book_to_out(b)


@router.delete("/{bid}")
async def delete_book(bid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b = await db.scalar(select(Book).where(Book.id==bid,Book.user_id==u.id).with_for_update())
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    from app.models.product import WorkJob
    if await db.scalar(select(WorkJob.id).where(WorkJob.book_id==bid,WorkJob.status.in_(['queued','running']))):
        raise HTTPException(409,'作品有未完成任务，请等待或取消后再删除')
    from app.services.storage.project_cleanup import delete_project
    await delete_project(db,b)
    await db.commit()
    return {"ok": True}


# ===== volumes =====
@router.get("/{bid}/volumes", response_model=list[VolumeOut])
async def list_volumes(bid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    rs = await db.scalars(select(Volume).where(Volume.book_id == bid).order_by(Volume.sort, Volume.id))
    return list(rs)


@router.post("/{bid}/volumes", response_model=VolumeOut)
async def create_volume(bid: int, data: VolumeIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    v = Volume(book_id=bid, name=data.name, sort=data.sort)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


@router.get("/{bid}/export")
async def export_book(bid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """导出当前用户拥有的整本正文，不输出模型密钥、对话或运营数据。"""
    import re
    from html import unescape
    from urllib.parse import quote
    from fastapi.responses import Response
    book = await db.get(Book, bid)
    if not book or book.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    chapters = list(await db.scalars(select(Chapter).where(Chapter.book_id == bid).order_by(Chapter.number)))
    if not any(c.content for c in chapters):
        raise HTTPException(400, "尚无可导出的章节正文")
    parts = [f"# {book.title}\n"]
    for ch in chapters:
        text = unescape(re.sub(r"<[^>]+>", "", re.sub(r"</p\s*>", "\n\n", ch.content or "", flags=re.I)))
        parts.append(f"## 第{ch.number}章 {ch.title}\n\n{text}\n")
    return Response("\n".join(parts), media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(book.title + ".md")})
