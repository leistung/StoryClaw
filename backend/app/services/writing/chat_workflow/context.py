from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Chapter
from app.models import Message
from app.models import User
from app.services.knowledge.memory import load_user_memory
from app.services.platform.skill_loader import build_write_context


def _model_choice(u: User, choice: dict | None) -> dict:
    """从前端 llm_choice 解析出 graph 用的 model_choice dict。"""
    return {"kind": "business", "model_id": (choice or {}).get("model_id")}


async def _build_input(
    u: User, message: str, thread_id: str, model_choice: dict,
    book_id: int | None, chapter_id: int | None, db: AsyncSession,
) -> dict:
    """构造 graph 输入 state（含历史消息合并）。"""
    # 加载历史消息（短期记忆）
    history = await db.scalars(select(Message).where(
        Message.thread_id == thread_id, Message.user_id == u.id
    ).order_by(Message.id))
    msgs = [{"role": m.role, "content": m.content} for m in history]
    msgs.append({"role": "user", "content": message})

    # 长期记忆
    user_mem = await load_user_memory(u.id, db)

    # 解析续写下一章：消息含"续写下一章/写下一章"时自动定位下一章
    resolved_chapter_id = chapter_id
    if book_id and ("续写下一章" in message or "写下一章" in message):
        next_ch = await _find_next_chapter(book_id, chapter_id, db)
        if next_ch:
            resolved_chapter_id = next_ch

    # 写作上下文（write-chapter skill）
    context: dict = {}
    current_content = ""
    if book_id and resolved_chapter_id:
        context = await build_write_context(u.id, book_id, resolved_chapter_id, db)
        ch = await db.get(Chapter, resolved_chapter_id)
        if ch and ch.content:
            current_content = ch.content

    return {
        "user_id": u.id,
        "book_id": book_id,
        "chapter_id": resolved_chapter_id,
        "thread_id": thread_id,
        "messages": msgs,
        "model_choice": model_choice,
        "user_memory": user_mem,
        "context": context,
        "current_content": current_content,
    }


async def _find_next_chapter(book_id: int, current_chapter_id: int | None, db: AsyncSession) -> int | None:
    """根据当前章节定位下一章 ID。"""
    if not current_chapter_id:
        first = await db.scalar(select(Chapter).where(
            Chapter.book_id == book_id, Chapter.number == 1
        ))
        return first.id if first else None
    cur = await db.get(Chapter, current_chapter_id)
    if not cur:
        return None
    nxt = await db.scalar(select(Chapter).where(
        Chapter.book_id == book_id, Chapter.number == cur.number + 1
    ))
    return nxt.id if nxt else None


def _extract_book_id(message: str) -> int | None:
    """从前端消息里解析 book_id（约定格式：[book:123]）。"""
    import re
    m = re.search(r"\[book:(\d+)\]", message or "")
    return int(m.group(1)) if m else None


def _extract_chapter_id(message: str) -> int | None:
    import re
    m = re.search(r"\[chapter:(\d+)\]", message or "")
    return int(m.group(1)) if m else None


