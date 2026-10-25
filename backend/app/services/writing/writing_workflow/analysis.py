from __future__ import annotations
import re
import uuid
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.runtime.execution import run_agent
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import Message
from app.models import User
from app.schemas import AnalyzeIn
from app.schemas import AnalyzeOut
from app.services.knowledge.memory import load_user_memory
from app.services.platform.metering import metered

from .context import _load_book_meta
from .context import _load_outline
from .context import _model_choice
from .context import _save_assistant_msg

async def analyze_book(
    bid: int, data: AnalyzeIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分析 skill 统一入口：plot/character/consistency/summary/outline。"""
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")

    if data.skill=='plot-planning':
        from app.services.writing.planning import require_outline
        await require_outline(db,bid)

    valid_skills = {"plot-planning", "character-development", "consistency-check",
                    "book-summary", "outline-planning"}
    if data.skill not in valid_skills:
        raise HTTPException(400, f"未知分析 skill: {data.skill}，可选：{valid_skills}")

    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[{data.skill}] 书籍 {bid}" +
                         (f" 角色：{data.character_name}" if data.character_name else "") +
                         (f" 范围：{data.chapter_range}" if data.chapter_range else ""))
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)
    book_meta = await _load_book_meta(db, bid, u)
    outline = await _load_outline(db, bid)

    # 加载章节内容摘要（consistency-check / book-summary 需要）
    chapters_brief = ""
    if data.skill in {"consistency-check", "book-summary"}:
        cr = data.chapter_range or {"start": 1, "end": 10}
        rs = await db.scalars(select(Chapter).where(
            Chapter.book_id == bid,
            Chapter.number >= int(cr.get("start", 1)),
            Chapter.number <= int(cr.get("end", 10)),
        ).order_by(Chapter.number))
        selected_chapters = list(rs)
        evidence_limit = min(2400, max(200, 18000 // max(1, len(selected_chapters)) - 60))
        parts = []
        for c in selected_chapters:
            if c.content:
                txt = re.sub(r"<[^>]+>", "", c.content)
                txt = re.sub(r"\s+", "", txt)
                excerpt = txt if len(txt) <= evidence_limit else txt[:evidence_limit//2] + " … " + txt[-evidence_limit//2:]
                parts.append(f"第{c.number}章 {c.title}：{excerpt}")
        chapters_brief = "\n\n".join(parts) or "（无章节内容）"

    input_state = {
        "user_id": u.id, "book_id": bid, "chapter_id": None,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": um.content}],
        "model_choice": mc, "user_memory": user_mem,
        "context": {
            "book_meta": book_meta,
            "outline": outline,
            "chapters_brief": chapters_brief,
            "character_name": data.character_name or book_meta.get("protagonist_name", ""),
            "character_intro": book_meta.get("protagonist_intro", ""),
            "chapter_range": data.chapter_range or {},
        },
        "active_skill": data.skill,
        "chapter_range": data.chapter_range or {},
        "intent": "analyze",
    }
    final = await run_agent(input_state, thread_id)

    report = final.get("analysis_report", "") or ""
    if not report:
        raise HTTPException(500, f"分析失败：{final.get('error', '未返回报告')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""

    am, cost = await _save_assistant_msg(db, u, thread_id, report, model_id, in_t, out_t, um.id)
    return AnalyzeOut(report=report, model=model_id, in_tokens=in_t, out_tokens=out_t,
                      credits_cost=cost, thread_id=thread_id, message_id=am.id)


analyze_book = metered(analyze_book)

