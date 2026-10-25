from __future__ import annotations
import asyncio
import uuid
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.services.writing.revisions import snapshot
from app.services.writing.revisions import assert_editable
from app.services.writing.revisions import chapter_hash
from app.services.writing.revisions import guard_write
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.runtime.deps import set_stream_sink
from storyclaw.runtime.execution import run_agent
from storyclaw.runtime.execution import sse
from storyclaw.runtime.execution import stream_agent
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import CreditsLedger
from app.models import Message
from app.models import User
from app.schemas import ChapterGenerateIn
from app.schemas import ChapterGenerateOut
from app.services.platform.credits import debit
from app.services.platform import pricing as pricing_svc
from app.services.platform.metering import metered

from .context import _build_input
from .context import _model_choice

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

    from app.services.writing.planning import require_outline
    from app.services.writing.planning import require_previous_memory
    await require_outline(db,b.id)
    from app.services.writing.serial import require_blueprint
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

    from app.services.writing.generation_candidates import preserve
    await preserve(db,u,c,final,base_hash,thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(502,"模型未返回可用正文，原稿未覆盖，请核对用量后重试")
    tu = final.get("token_usage") or {}
    in_t = int(tu.get("in_tokens", 0) or 0)
    out_t = int(tu.get("out_tokens", 0) or 0)
    model_id = tu.get("model_id", "") or ""

    # 写回章节
    from storyclaw.context.builder import count_words
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
    from app.services.writing.setting_sync import launch as launch_setting_sync
    launch_setting_sync(b.id, c.id, u.id, model_choice)
    return ChapterGenerateOut(
        chapter_id=c.id, title=c.title, content=content, word_count=c.word_count,
        model=model_id, in_tokens=in_t, out_tokens=out_t, credits_cost=cost,
        thread_id=thread_id, message_id=am.id, review_feedback=final.get("review_feedback", ""),
    )


generate_chapter = metered(generate_chapter)

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

    from app.services.writing.planning import require_outline
    from app.services.writing.planning import require_previous_memory
    await require_outline(db,b.id)
    from app.services.writing.serial import require_blueprint
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
                from app.services.writing.generation_candidates import preserve
                from app.database import AsyncSessionLocal
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

            from storyclaw.context.builder import count_words
            from app.database import AsyncSessionLocal
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
                from app.services.writing.setting_sync import launch as launch_setting_sync
                launch_setting_sync(b.id, cid, u.id, model_choice)
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            set_stream_sink(None)

    return StreamingResponse(gen(), media_type="text/event-stream")


generate_chapter_stream = metered(generate_chapter_stream)

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

    from app.services.writing.planning import require_outline
    from app.services.writing.planning import require_previous_memory
    await require_outline(db,b.id)
    from app.services.writing.serial import require_blueprint
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

    from app.services.writing.generation_candidates import preserve
    await preserve(db,u,c,final,base_hash,thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(502,"模型未返回可用内容，未覆盖正文，请核对记录后再试")
    tu = final.get("token_usage") or {}
    in_t = int(tu.get("in_tokens", 0) or 0)
    out_t = int(tu.get("out_tokens", 0) or 0)
    model_id = tu.get("model_id", "") or ""

    from storyclaw.context.builder import count_words
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


modify_chapter = metered(modify_chapter)

