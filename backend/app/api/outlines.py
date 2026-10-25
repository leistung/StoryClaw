import json
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.deps import get_current_user
from ..database import get_db
from ..models import Book, ConfigEntity, Outline, User
from ..schemas import OutlineOut, OutlineUpdateIn

from ..services.planning import assert_planning_editable, outline_hash, is_confirmed

router = APIRouter(prefix="/books", tags=["outlines"])


async def _get_owned_book(bid: int, u: User, db: AsyncSession) -> Book:
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    return b


async def _call_langgraph(meta: dict) -> tuple[dict, str | None]:
    from storyclaw.outline import generate_outline as infer
    try:return await infer(meta)
    except ValueError as exc:raise HTTPException(502,str(exc)) from exc


@router.post("/{bid}/outline/generate", response_model=OutlineOut)
async def generate_outline(bid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), mode:Literal['serial','fixed']='fixed'):
    b = await _get_owned_book(bid, u, db)
    await assert_planning_editable(db,bid)
    meta = {
        "planning_mode":mode,
        "title": b.title, "intro": b.intro or "", "genre": b.genre,
        "protagonist_name": b.protagonist_name or "", "protagonist_intro": b.protagonist_intro or "",
        "target_chapters": b.target_chapters, "target_words": b.target_words,
        "per_chapter_words": b.per_chapter_words,
    }
    canon = list(await db.scalars(select(ConfigEntity).where(
        ConfigEntity.book_id == bid,
        ConfigEntity.entity_type.in_(["character", "scene", "item", "world"]),
    ).order_by(ConfigEntity.sort_order, ConfigEntity.id).limit(40)))
    meta["canon"] = [{"type": r.entity_type, "name": r.name,
                      "description": (r.description or "")[:400]} for r in canon]
    outline, err = await _call_langgraph(meta)
    outline.pop('_review',None)
    existing = await db.scalar(select(Outline).where(Outline.book_id == bid))
    if existing:
        from ..services.serial import invalidate_book
        await invalidate_book(db,bid,'故事总纲已重新生成，请复核既有正文与后续章纲')
        existing.content = json.dumps(outline, ensure_ascii=False)
    else:
        existing = Outline(book_id=bid, content=json.dumps(outline, ensure_ascii=False))
        db.add(existing)
    await db.commit()
    await db.refresh(existing)
    return OutlineOut(id=existing.id, book_id=existing.book_id, content=outline, error=err,
                      created_at=existing.created_at, updated_at=existing.updated_at)


@router.get("/{bid}/outline", response_model=OutlineOut)
async def get_outline(bid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_book(bid, u, db)
    o = await db.scalar(select(Outline).where(Outline.book_id == bid))
    if not o:
        raise HTTPException(404, "大纲不存在，请先生成")
    try:
        content = json.loads(o.content) if o.content else {}
    except Exception:
        content = {"raw": o.content}
    return OutlineOut(id=o.id, book_id=o.book_id, content=content,
                      created_at=o.created_at, updated_at=o.updated_at)


@router.put("/{bid}/outline", response_model=OutlineOut)
async def update_outline(bid: int, data: OutlineUpdateIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b=await _get_owned_book(bid, u, db)
    await db.refresh(b,with_for_update=True)
    o = await db.scalar(select(Outline).where(Outline.book_id == bid))
    await assert_planning_editable(db,bid)
    content=dict(data.content)
    content.pop('_review',None)
    if o and outline_hash(json.loads(o.content))!=outline_hash(content):
        from ..services.serial import invalidate_book
        await invalidate_book(db,bid,'故事总纲或阶段目标已变更，请复核既有正文和后续章纲')
    content_str = json.dumps(content, ensure_ascii=False)
    if o:
        o.content = content_str
    else:
        o = Outline(book_id=bid, content=content_str)
        db.add(o)
    await db.commit()
    await db.refresh(o)
    return OutlineOut(id=o.id, book_id=o.book_id, content=content,
                      created_at=o.created_at, updated_at=o.updated_at)


@router.post("/{bid}/outline/confirm", response_model=OutlineOut)
async def confirm_outline(bid: int, data: OutlineUpdateIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b=await _get_owned_book(bid,u,db)
    await db.refresh(b,with_for_update=True)
    await assert_planning_editable(db,bid)
    row=await db.scalar(select(Outline).where(Outline.book_id==bid).with_for_update())
    if not row:raise HTTPException(409,'请先保存大纲')
    content=json.loads(row.content)
    if outline_hash(content)!=outline_hash(data.content):raise HTTPException(409,'大纲已变更，请重新加载或保存后再确认')
    from storyclaw.outline import validate_confirmation
    try:validate_confirmation(content)
    except (ValueError,TypeError,AttributeError) as exc:raise HTTPException(400,'大纲结构不完整：'+str(exc)) from exc
    content['_review']={'hash':outline_hash(content),'confirmed_at':datetime.now(timezone.utc).isoformat(),'user_id':u.id}
    row.content=json.dumps(content,ensure_ascii=False)
    await db.commit();await db.refresh(row)
    return OutlineOut(id=row.id,book_id=bid,content=content,created_at=row.created_at,updated_at=row.updated_at)
