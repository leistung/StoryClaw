from __future__ import annotations
import uuid
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.context.builder import count_words
from storyclaw.runtime.execution import run_agent
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import Message
from app.models import User
from app.schemas import ContinueIn
from app.schemas import ContinueOut
from app.schemas import PolishIn
from app.schemas import PolishOut
from app.services.knowledge.memory import load_user_memory
from app.services.platform.skill_loader import build_write_context
from app.services.platform.metering import metered

from .context import _model_choice
from .context import _save_assistant_msg

async def polish_chapter(
    cid: int, data: PolishIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """polish-chapter skill：对选中文本做文笔润色。"""
    c = await db.get(Chapter, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    b = await db.get(Book, c.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "章节不存在")
    if not data.selected_text.strip():
        raise HTTPException(400, "待润色文本不能为空")

    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[润色] {data.polish_goal or '提升文笔'}：{data.selected_text[:100]}...")
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)
    ctx = await build_write_context(u.id, c.book_id, cid, db)

    input_state = {
        "user_id": u.id, "book_id": c.book_id, "chapter_id": cid,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": data.selected_text}],
        "model_choice": mc, "user_memory": user_mem, "context": ctx,
        "intent": "polish",
        "selected_text": data.selected_text,
        "polish_goal": data.polish_goal or "提升文笔与画面感",
        "current_content": c.content or "",
    }
    final = await run_agent(input_state, thread_id)

    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(500, f"润色失败：{final.get('error', '未返回内容')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""

    am, cost = await _save_assistant_msg(db, u, thread_id, content, model_id, in_t, out_t, um.id)
    return PolishOut(content=content, word_count=count_words(content), model=model_id,
                     in_tokens=in_t, out_tokens=out_t, credits_cost=cost,
                     thread_id=thread_id, message_id=am.id)


polish_chapter = metered(polish_chapter)

async def continue_writing(
    cid: int, data: ContinueIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """continue-writing skill：基于光标前文续写片段。"""
    c = await db.get(Chapter, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    b = await db.get(Book, c.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "章节不存在")

    prefix = data.prefix_text or ""
    if not prefix and c.content:
        prefix = c.content[-1500:]

    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[续写片段] 光标前：{prefix[-80:]}...")
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)
    ctx = await build_write_context(u.id, c.book_id, cid, db)

    ctx["fragment_max_words"] = data.max_words
    ctx['author_instruction']=data.instruction
    if data.cursor_offset is not None:
        from storyclaw.workflows.continuity import prose
        full=prose(c.content)
        if data.cursor_offset>len(full):raise HTTPException(409,'续写位置超出本章正文范围')
        prefix=full[:data.cursor_offset]
        ctx['cursor_offset']=data.cursor_offset
        ctx['continuation_suffix']=full[data.cursor_offset:]
    input_state = {
        "user_id": u.id, "book_id": c.book_id, "chapter_id": cid,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": data.instruction or "请基于上文续写片段"}],
        "model_choice": mc, "user_memory": user_mem, "context": ctx,
        "intent": "continue",
        "prefix_text": prefix,
        "current_content": c.content or "",
    }
    final = await run_agent(input_state, thread_id)

    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(500, f"续写失败：{final.get('error', '未返回内容')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""

    am, cost = await _save_assistant_msg(db, u, thread_id, content, model_id, in_t, out_t, um.id)
    return ContinueOut(content=content, word_count=count_words(content), model=model_id,
                       in_tokens=in_t, out_tokens=out_t, credits_cost=cost,
                       thread_id=thread_id, message_id=am.id)


continue_writing = metered(continue_writing)

