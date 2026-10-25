from __future__ import annotations
import json
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Book
from app.models import CreditsLedger
from app.models import Message
from app.models import Outline
from app.models import User
from app.services.platform.credits import debit
from app.services.platform import pricing as pricing_svc


def _model_choice(u: User, choice: dict | None) -> dict:
    return {"kind": "business", "model_id": (choice or {}).get("model_id")}


async def _save_assistant_msg(db: AsyncSession, u: User, thread_id: str,
                              content: str, model_id: str, in_t: int, out_t: int,
                              ref_user_msg_id: int | None = None) -> tuple[Message, int]:
    """保存 assistant 消息 + 扣积分。返回 (message, credits_cost)。"""
    u2 = await db.get(User, u.id)
    cost = 0
    if u2.version == "business":
        cost = pricing_svc.compute_cost(model_id, in_t, out_t)
        await debit(db, u2, cost)
        db.add(CreditsLedger(user_id=u2.id, delta=-cost, reason="consume", model=model_id,
                             in_tokens=in_t, out_tokens=out_t, ref_msg_id=ref_user_msg_id))
    am = Message(user_id=u2.id, thread_id=thread_id, role="assistant", content=content,
                 model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost)
    db.add(am)
    await db.commit()
    await db.refresh(am)
    await db.refresh(u2)
    return am, cost


async def _load_outline(db: AsyncSession, book_id: int) -> dict:
    row = await db.scalar(select(Outline).where(Outline.book_id == book_id))
    if row and row.content:
        try:
            return json.loads(row.content) if isinstance(row.content, str) else row.content
        except Exception:
            return {}
    return {}


async def _load_book_meta(db: AsyncSession, book_id: int, u: User) -> dict:
    b = await db.get(Book, book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    return {
        "id": b.id, "title": b.title, "genre": b.genre or "",
        "intro": b.intro or "", "protagonist_name": b.protagonist_name or "",
        "protagonist_intro": b.protagonist_intro or "",
        "target_chapters": b.target_chapters, "target_words": b.target_words,
        "per_chapter_words": b.per_chapter_words,
    }


