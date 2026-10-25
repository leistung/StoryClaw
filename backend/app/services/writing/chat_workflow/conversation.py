from __future__ import annotations
import uuid
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.runtime.execution import run_agent
from storyclaw.runtime.execution import sse
from storyclaw.runtime.execution import stream_agent
from app.core.deps import get_current_user
from app.database import get_db
from app.models import CreditsLedger
from app.models import Message
from app.models import User
from app.schemas import ChatIn
from app.schemas import ChatOut
from app.services.platform.credits import debit
from app.services.platform import pricing as pricing_svc
from app.services.platform.metering import metered

from .context import _build_input
from .context import _extract_book_id
from .context import _extract_chapter_id
from .context import _model_choice

async def chat(data: ChatIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """非流式对话：调用 Agent 图。"""
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user", content=data.message)
    db.add(um)
    await db.commit()
    await db.refresh(um)

    book_id = data.book_id or _extract_book_id(data.message)
    chapter_id = data.chapter_id or _extract_chapter_id(data.message)
    from storyclaw.contracts import Scope
    from app.services.agent.agent_runs import validate_scope
    await validate_scope(db,u.id,Scope(book_id=book_id,chapter_id=chapter_id))

    model_choice = _model_choice(u, data.llm_choice)
    input_state = await _build_input(u, data.message, thread_id, model_choice, book_id, chapter_id, db)

    try:
        final = await run_agent(input_state, thread_id)
    except Exception as e:
        raise HTTPException(500, f"Agent 调用失败: {e}")

    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(502,"模型未返回可用内容，未覆盖正文，请核对记录后再试")
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
    am = Message(user_id=u2.id, thread_id=thread_id, role="assistant", content=content,
                 model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost)
    db.add(am)
    await db.commit()
    await db.refresh(am)
    await db.refresh(u2)
    return ChatOut(thread_id=thread_id, message_id=am.id, content=content, model=model_id,
                   in_tokens=in_t, out_tokens=out_t, credits_cost=cost)


chat = metered(chat)

async def chat_stream(data: ChatIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """SSE 流式：节点级推送，最终 done 事件聚合结果。"""
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user", content=data.message)
    db.add(um)
    await db.commit()
    await db.refresh(um)

    book_id = data.book_id or _extract_book_id(data.message)
    chapter_id = data.chapter_id or _extract_chapter_id(data.message)
    from storyclaw.contracts import Scope
    from app.services.agent.agent_runs import validate_scope
    await validate_scope(db,u.id,Scope(book_id=book_id,chapter_id=chapter_id))

    model_choice = _model_choice(u, data.llm_choice)
    input_state = await _build_input(u, data.message, thread_id, model_choice, book_id, chapter_id, db)

    async def gen():
        final: dict = {}
        try:
            yield sse("start", {"thread_id": thread_id, "intent_preview": "routing"})
            async for node, diff in stream_agent(input_state, thread_id):
                final.update(diff)
                evt = {"node": node}
                if "intent" in diff:
                    evt["intent"] = diff["intent"]
                if diff.get("draft_content"):
                    evt["content"] = diff["draft_content"]
                if "review_feedback" in diff:
                    evt["review_feedback"] = diff["review_feedback"]
                    evt["review_round"] = diff.get("review_round", 0)
                if "active_skill" in diff:
                    evt["active_skill"] = diff["active_skill"]
                if "status" in diff:
                    evt["status"] = diff["status"]
                yield sse("state", evt)

            if final.get('error') or final.get('status')=='error':
                yield sse('error',{'message':final.get('error') or '生成中断'});return
            content = final.get("draft_content", "") or ""
            tu = final.get("token_usage") or {}
            in_t = int(tu.get("in_tokens", 0) or 0)
            out_t = int(tu.get("out_tokens", 0) or 0)
            model_id = tu.get("model_id", "") or ""

            # 落库 + 积分扣减（重新查询 User 避免 detached）
            u2 = await db.get(User, u.id)
            cost = 0
            if u2.version == "business":
                cost = pricing_svc.compute_cost(model_id, in_t, out_t)
                await debit(db, u2, cost)
                db.add(CreditsLedger(user_id=u2.id, delta=-cost, reason="consume", model=model_id,
                                     in_tokens=in_t, out_tokens=out_t, ref_msg_id=um.id))
            am = Message(user_id=u2.id, thread_id=thread_id, role="assistant", content=content,
                         model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost)
            db.add(am)
            await db.commit()
            await db.refresh(am)
            await db.refresh(u2)

            yield sse("done", {
                "thread_id": thread_id,
                "message_id": am.id,
                "content": content,
                "model": model_id,
                "in_tokens": in_t,
                "out_tokens": out_t,
                "credits_cost": cost,
                "review_feedback": final.get("review_feedback", ""),
                "active_skill": final.get("active_skill"),
                "credits_balance": u2.credits_balance,
            })
        except Exception as e:
            await db.rollback()
            yield sse("error", {"message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


chat_stream = metered(chat_stream)

