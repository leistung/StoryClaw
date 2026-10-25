import hashlib
import json
from contextvars import ContextVar
from fastapi import HTTPException
from sqlalchemy import select
from app.models.product import ChapterRevision
from app.models.product import WorkJob

current_job_id = ContextVar('current_job_id', default=None)

def chapter_hash(chapter):
    return hashlib.sha256(json.dumps([chapter.title,chapter.content],ensure_ascii=False).encode()).hexdigest()

async def assert_editable(db, cid):
    from app.models import Chapter
    bid=select(Chapter.book_id).where(Chapter.id==cid).scalar_subquery()
    query=select(WorkJob.id).where(WorkJob.book_id==bid,WorkJob.status.in_(['queued','running']))
    if current_job_id.get():query=query.where(WorkJob.id!=current_job_id.get())
    if await db.scalar(query):raise HTTPException(409,'该章节有待执行或运行中的任务，请等待任务完成后编辑')

async def snapshot(db, chapter, source):
    from app.services.library.library import invalidate_import
    await invalidate_import(db,chapter)
    from app.services.writing.serial import invalidate_following
    await invalidate_following(db,chapter,f'第{chapter.number}章正文或标题已变更，请复核后文')
    if not chapter.content and not chapter.title:return
    latest=await db.scalar(select(ChapterRevision).where(ChapterRevision.chapter_id==chapter.id).order_by(ChapterRevision.id.desc()).limit(1))
    digest=chapter_hash(chapter)
    if latest and latest.content_hash==digest:return
    db.add(ChapterRevision(chapter_id=chapter.id,title=chapter.title,content=chapter.content,word_count=chapter.word_count,content_hash=digest,source=source))

async def guard_write(db,chapter,expected_hash,expected_context=None):
    from app.models import Book
    book=await db.get(Book,chapter.book_id)
    await db.refresh(book,with_for_update=True)
    if expected_context:
        from app.services.writing.serial import inputs
        if (await inputs(db,chapter))[3]!=expected_context:raise HTTPException(409,'生成期间前文或设定已变化，结果未覆盖正文，请重新核对')
    await db.refresh(chapter,with_for_update=True)
    if chapter_hash(chapter)!=expected_hash:
        raise HTTPException(409,'生成期间正文已被修改，本次结果未覆盖原稿；请核对后重新生成')
