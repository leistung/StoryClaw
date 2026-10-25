"""Chat & Agent Loop API（薄网关）。

Agent 执行统一走 packages/storyclaw/src/storyclaw/runtime（run_agent / stream_agent），
本模块只负责：鉴权 / 消息落库 / 积分计费 / SSE 格式 / 上下文组装。
- POST /chat           非流式调用 Agent
- POST /chat/stream    SSE 流式：节点级推送，最终 done 事件包含 token/积分
- POST /chapters/{cid}/generate  章节生成（write-chapter skill 入口）
- GET  /messages       按 thread_id 列出消息历史
- POST /messages/{mid}/retry     重试
- PATCH /messages/{mid}/feedback 反馈
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from ..services.revisions import snapshot, assert_editable, chapter_hash, guard_write
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from storyclaw.deps import set_stream_sink
from storyclaw.runtime import run_agent, sse, stream_agent

from ..core.deps import get_current_user
from ..database import get_db
from ..models import Book, Chapter, CreditsLedger, Message, User
from ..schemas import (
    ChatIn, ChatOut, ChapterGenerateIn, ChapterGenerateOut, FeedbackIn,
)
from ..services.credits import debit
from ..services import pricing as pricing_svc
from ..services.memory import load_user_memory
from ..services.skill_loader import build_write_context



# ============ Agent 调用辅助 ============

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


# ============ 端点 ============

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
    from ..services.agent_runs import validate_scope
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
    from ..services.agent_runs import validate_scope
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


async def generate_chapter(cid: int, data: ChapterGenerateIn,
                           u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """章节生成入口（write-chapter skill）。

    调用 Agent 图，supervisor 检测到"写本章/续写"关键词自动路由到 writer 子图。
    生成内容写入 Chapter.content，并更新 word_count。
    """
    c = await db.get(Chapter, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    b = await db.get(Book, c.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "章节不存在")

    from ..services.planning import require_outline, require_previous_memory
    await require_outline(db,b.id)
    from ..services.serial import require_blueprint
    await require_blueprint(db,c)
    await require_previous_memory(db,c)
    await assert_editable(db, cid)
    base_hash=chapter_hash(c)
    prompt = data.prompt or f"请写本章：{c.title}"
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user", content=prompt)
    db.add(um)
    await db.commit()
    await db.refresh(um)

    model_choice = _model_choice(u, data.llm_choice)
    # 强制带"写本章"关键词触发 writer 路由
    routing_msg = f"写本章 {prompt}" if "写本章" not in prompt else prompt
    input_state = await _build_input(u, routing_msg, thread_id, model_choice, b.id, c.id, db)
    input_state["intent"] = "write"

    try:
        final = await run_agent(input_state, thread_id)
    except Exception as e:
        raise HTTPException(500, f"Agent 调用失败: {e}")

    from .generation_candidates import preserve
    await preserve(db,u,c,final,base_hash,thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(502,"模型未返回可用正文，原稿未覆盖，请核对用量后重试")
    tu = final.get("token_usage") or {}
    in_t = int(tu.get("in_tokens", 0) or 0)
    out_t = int(tu.get("out_tokens", 0) or 0)
    model_id = tu.get("model_id", "") or ""

    # 写回章节
    from storyclaw.context import count_words
    wc = count_words(content)
    await guard_write(db,c,base_hash,(input_state.get("context") or {}).get("dependency_hash"))
    await snapshot(db, c, "ai")
    c.content = content
    c.word_count = wc
    c.rag_status = "pending"

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
    await db.refresh(c)
    await db.refresh(am)
    await db.refresh(u2)
    # 后台同步：从本章内容提取并更新 角色/场景/物品/情节 设定
    from ..services.setting_sync import launch as launch_setting_sync
    launch_setting_sync(b.id, c.id, u.id, model_choice)
    return ChapterGenerateOut(
        chapter_id=c.id, title=c.title, content=content, word_count=c.word_count,
        model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost,
        thread_id=thread_id, message_id=am.id, review_feedback=final.get("review_feedback", ""),
    )


async def generate_chapter_stream(cid: int, data: ChapterGenerateIn,
                                  u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """章节生成 SSE 流式版：writer 节点逐 token 推送 draft，节点级进展推送 node。

    事件流：
      event: start  -> {thread_id, chapter_id}
      event: node   -> {node: "supervisor"|"reviewer"|...} 节点进展
      event: draft  -> {delta: "文本增量"} 逐 token 正文
      event: done   -> {content, word_count, model, in_tokens, out_tokens, credits_cost, thread_id, message_id}
      event: error  -> {message}
    """
    c = await db.get(Chapter, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    b = await db.get(Book, c.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "章节不存在")

    from ..services.planning import require_outline, require_previous_memory
    await require_outline(db,b.id)
    from ..services.serial import require_blueprint
    await require_blueprint(db,c)
    await require_previous_memory(db,c)
    await assert_editable(db, cid)
    base_hash=chapter_hash(c)
    prompt = data.prompt or f"请写本章：{c.title}"
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user", content=prompt)
    db.add(um)
    await db.commit()
    await db.refresh(um)

    model_choice = _model_choice(u, data.llm_choice)
    routing_msg = f"写本章 {prompt}" if "写本章" not in prompt else prompt
    input_state = await _build_input(u, routing_msg, thread_id, model_choice, b.id, c.id, db)
    input_state["intent"] = "write"

    queue: asyncio.Queue = asyncio.Queue()

    async def sink(event: str, payload: dict):
        await queue.put((event, payload))

    async def agent_run():
        final: dict = {}
        try:
            async for node, diff in stream_agent(input_state, thread_id):
                if isinstance(diff, dict):
                    final.update(diff)
                    if node in ("supervisor", "reviewer", "researcher", "analyst", "chat", "assistant", "plan_outline"):
                        await queue.put(("node", {"node": node}))
        except Exception as e:  # noqa: BLE001
            await queue.put(("error", {"message": f"Agent 调用失败: {e}"}))
            return
        await queue.put(("agent_done", {"final": final}))

    async def gen():
        set_stream_sink(sink)
        task = asyncio.create_task(agent_run())
        final: dict = {}
        try:
            yield sse("start", {"thread_id": thread_id, "chapter_id": cid})
            while True:
                event, payload = await queue.get()
                if event == "agent_done":
                    final = payload["final"]
                    break
                if event == "error":
                    yield sse("error", payload)
                    task.cancel()
                    return
                yield sse(event, payload)

            if final.get('error') or final.get('status')=='error':
                from .generation_candidates import preserve
                from ..database import AsyncSessionLocal
                async with AsyncSessionLocal() as candidate_db:
                    candidate_user=await candidate_db.get(User,u.id);candidate_chapter=await candidate_db.get(Chapter,cid)
                    if candidate_user and candidate_chapter:
                        try:await preserve(candidate_db,candidate_user,candidate_chapter,final,base_hash,thread_id)
                        except HTTPException as exc:
                            yield sse('error',{'message':str(exc.detail),'thread_id':thread_id});return
                yield sse('error',{'message':'生成中断，未覆盖正文'});return
            content = final.get("draft_content", "") or ""
            if not content:
                yield sse("error", {"message": "Agent 未返回内容"})
                return
            tu = final.get("token_usage") or {}
            in_t = int(tu.get("in_tokens", 0) or 0)
            out_t = int(tu.get("out_tokens", 0) or 0)
            model_id = tu.get("model_id", "") or ""

            from storyclaw.context import count_words
            from ..database import AsyncSessionLocal
            # 用独立 session 落库：请求级 db session 在 SSE 生成器执行时已失效
            done_payload = None
            async with AsyncSessionLocal() as sdb:
                c2 = await sdb.get(Chapter, cid)
                if c2 is None:
                    yield sse("error", {"message": "章节不存在"})
                    return
                wc = count_words(content)
                try:
                    await guard_write(sdb,c2,base_hash,(input_state.get("context") or {}).get("dependency_hash"))
                except HTTPException as exc:
                    yield sse('error',{'message':str(exc.detail)})
                    return
                await snapshot(sdb, c2, "ai")
                c2.content = content
                c2.word_count = wc
                c2.rag_status = "pending"
                u2 = await sdb.get(User, u.id)
                cost = 0
                if u2 and u2.version == "business":
                    cost = pricing_svc.compute_cost(model_id, in_t, out_t)
                    await debit(sdb, u2, cost)
                    sdb.add(CreditsLedger(user_id=u2.id, delta=-cost, reason="consume", model=model_id,
                                         in_tokens=in_t, out_tokens=out_t, ref_msg_id=um.id))
                am = Message(user_id=u.id, thread_id=thread_id, role="assistant", content=content,
                             model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost)
                sdb.add(am)
                await sdb.commit()
                await sdb.refresh(c2)
                await sdb.refresh(am)
                if u2:
                    await sdb.refresh(u2)
                done_payload = {
                    "chapter_id": c2.id, "title": c2.title, "content": content, "word_count": wc,
                    "model": model_id, "in_tokens": in_t, "out_tokens": out_t, "credits_cost": cost,
                    "thread_id": thread_id, "message_id": am.id,
                    "review_feedback": final.get("review_feedback", ""),
                }
            yield sse("done", done_payload)
            # 后台同步：从本章内容提取并更新 角色/场景/物品/情节 设定
            if done_payload:
                from ..services.setting_sync import launch as launch_setting_sync
                launch_setting_sync(b.id, cid, u.id, model_choice)
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            set_stream_sink(None)

    return StreamingResponse(gen(), media_type="text/event-stream")



async def modify_chapter(cid: int, data: ChapterGenerateIn,
                         u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """章节修改入口（modify-chapter skill）。

    基于当前章节内容 + 用户修改要求，重写整章。
    intent=modify，writer 走 _writer_modify 模式，reviewer 用 LLM 检查修改要求。
    """
    c = await db.get(Chapter, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    b = await db.get(Book, c.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "章节不存在")
    if not c.content:
        raise HTTPException(400, "章节尚未生成，无法修改。请先调用 /generate")

    from ..services.planning import require_outline, require_previous_memory
    await require_outline(db,b.id)
    from ..services.serial import require_blueprint
    await require_blueprint(db,c)
    await require_previous_memory(db,c)
    await assert_editable(db, cid)
    base_hash=chapter_hash(c)
    modify_req = data.prompt or "请润色优化本章"
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user", content=modify_req)
    db.add(um)
    await db.commit()
    await db.refresh(um)

    model_choice = _model_choice(u, data.llm_choice)
    # modify 路由：消息含"修改"关键词 + current_content 非空
    input_state = await _build_input(u, f"修改 {modify_req}", thread_id, model_choice, b.id, c.id, db)

    try:
        final = await run_agent(input_state, thread_id)
    except Exception as e:
        raise HTTPException(500, f"Agent 调用失败: {e}")

    from .generation_candidates import preserve
    await preserve(db,u,c,final,base_hash,thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(502,"模型未返回可用内容，未覆盖正文，请核对记录后再试")
    tu = final.get("token_usage") or {}
    in_t = int(tu.get("in_tokens", 0) or 0)
    out_t = int(tu.get("out_tokens", 0) or 0)
    model_id = tu.get("model_id", "") or ""

    from storyclaw.context import count_words
    wc = count_words(content)
    await guard_write(db,c,base_hash,(input_state.get("context") or {}).get("dependency_hash"))
    await snapshot(db, c, "ai")
    c.content = content
    c.word_count = wc
    c.rag_status = "pending"

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
    await db.refresh(c)
    await db.refresh(am)
    await db.refresh(u2)
    return ChapterGenerateOut(
        chapter_id=c.id, title=c.title, content=content, word_count=c.word_count,
        model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost,
        thread_id=thread_id, message_id=am.id, review_feedback=final.get("review_feedback", ""),
    )


# ============ 历史 / 重试 / 反馈 ============

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


# ============ 工具 ============

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

from .metering import metered
generate_chapter = metered(generate_chapter)
modify_chapter = metered(modify_chapter)

chat = metered(chat)
chat_stream = metered(chat_stream)
generate_chapter_stream = metered(generate_chapter_stream)
