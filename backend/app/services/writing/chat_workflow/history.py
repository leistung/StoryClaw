from __future__ import annotations
import uuid
from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.runtime.execution import run_agent
from app.core.deps import get_current_user
from app.database import get_db
from app.models import CreditsLedger
from app.models import Message
from app.models import User
from app.schemas import ChatOut
from app.schemas import FeedbackIn
from app.services.platform.credits import debit
from app.services.platform import pricing as pricing_svc

from .context import _build_input

async def list_sessions(u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """列出当前用户的所有 AI 对话会话（按 thread 分组，按最后活跃倒序）。

    每个会话返回：thread_id、首条消息摘要、消息数、最后活跃时间。
    """
    rows = (await db.execute(
        select(Message.thread_id, func.count(Message.id).label("msg_count"),
               func.max(Message.created_at).label("last_at"))
        .where(Message.user_id == u.id)
        .group_by(Message.thread_id)
        .order_by(func.max(Message.created_at).desc())
    )).all()
    if not rows:
        return []
    # 每个 thread 的首条消息作为标题摘要
    min_ids = select(func.min(Message.id)).where(Message.user_id == u.id).group_by(Message.thread_id)
    firsts = (await db.execute(
        select(Message.thread_id, Message.content)
        .where(Message.user_id == u.id, Message.id.in_(min_ids))
    )).all()
    title_map = {t: c.strip().replace("\n", " ") for t, c in firsts}
    out = []
    for r in rows:
        title = title_map.get(r.thread_id, "")
        if len(title) > 50:
            title = title[:50] + "…"
        out.append({
            "thread_id": r.thread_id,
            "title": title or "(空会话)",
            "msg_count": r.msg_count,
            "last_at": r.last_at.isoformat() if r.last_at else None,
        })
    return out


async def list_messages(thread_id: str, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rs = await db.scalars(select(Message).where(
        Message.thread_id == thread_id, Message.user_id == u.id
    ).order_by(Message.id))
    return [{
        "id": m.id, "role": m.role, "content": m.content, "model": m.model,
        "in_tokens": m.in_tokens, "out_tokens": m.out_tokens, "credits_cost": m.credits_cost,
        "feedback": m.feedback, "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in rs]


async def retry(mid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    am = await db.get(Message, mid)
    if not am or am.user_id != u.id or am.role != "assistant":
        raise HTTPException(404, "消息不存在")
    um = await db.scalar(select(Message).where(
        Message.thread_id == am.thread_id, Message.user_id == u.id,
        Message.role == "user", Message.id < am.id
    ).order_by(Message.id.desc()))
    if not um:
        raise HTTPException(400, "找不到原始提问")

    model_choice = {"kind": "business", "model_id": am.model}

    # 重试需要新的 thread_id 以避免 CheckPointer 命中历史
    new_tid = uuid.uuid4().hex
    input_state = await _build_input(u, um.content, new_tid, model_choice, None, None, db)

    try:
        final = await run_agent(input_state, new_tid)
    except Exception as e:
        raise HTTPException(500, f"Agent 调用失败: {e}")
    content = final.get("draft_content", "") or ""
    tu = final.get("token_usage") or {}
    in_t = int(tu.get("in_tokens", 0) or 0)
    out_t = int(tu.get("out_tokens", 0) or 0)
    model_id = tu.get("model_id", "") or ""

    u2 = await db.get(User, u.id)
    cost = 0
    if u2.version == "business":
        cost = pricing_svc.compute_cost(model_id, in_t, out_t)
        await debit(db, u2, cost)
        db.add(CreditsLedger(user_id=u2.id, delta=-cost, reason="consume", model=model_id,
                             in_tokens=in_t, out_tokens=out_t, ref_msg_id=um.id))
    am2 = Message(user_id=u2.id, thread_id=new_tid, role="assistant", content=content,
                  model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost)
    db.add(am2)
    await db.commit()
    await db.refresh(am2)
    await db.refresh(u2)
    return ChatOut(thread_id=new_tid, message_id=am2.id, content=content, model=model_id,
                   in_tokens=in_t, out_tokens=out_t, credits_cost=cost)


async def feedback(mid: int, data: FeedbackIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    m = await db.get(Message, mid)
    if not m or m.user_id != u.id:
        raise HTTPException(404, "消息不存在")
    m.feedback = data.feedback
    await db.commit()
    return {"ok": True}


