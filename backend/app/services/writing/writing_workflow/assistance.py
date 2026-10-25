from __future__ import annotations
import uuid
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.runtime.execution import run_agent
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Message
from app.models import User
from app.schemas import AssistOut
from app.schemas import BrainstormIn
from app.schemas import DialoguePolishIn
from app.schemas import ReadingConfigGenIn
from app.schemas import SceneEnhanceIn
from app.schemas import TitleGenIn
from app.services.knowledge.memory import load_user_memory
from app.services.platform.metering import metered

from .context import _model_choice
from .context import _save_assistant_msg

async def assist_brainstorm(
    data: BrainstormIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """brainstorm skill：头脑风暴生成创意建议。"""
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[头脑风暴] {data.topic}")
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)

    input_state = {
        "user_id": u.id, "book_id": None, "chapter_id": None,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": f"主题：{data.topic}\n方向：{data.direction or '不限'}"}],
        "model_choice": mc, "user_memory": user_mem,
        "context": {"count": data.count, "genre": data.genre, "direction": data.direction},
        "active_skill": "brainstorm", "intent": "assist",
    }
    final = await run_agent(input_state, thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(500, f"头脑风暴失败：{final.get('error', '未返回内容')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""
    am, cost = await _save_assistant_msg(db, u, thread_id, content, model_id, in_t, out_t, um.id)
    return AssistOut(content=content, model=model_id, in_tokens=in_t, out_tokens=out_t,
                     credits_cost=cost, thread_id=thread_id, message_id=am.id)


assist_brainstorm = metered(assist_brainstorm)

async def assist_title_generation(
    data: TitleGenIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """title-generation skill：生成候选标题列表。"""
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[标题生成] {data.target} 风格={data.style}")
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)
    user_msg = f"请生成{data.count}个{data.style}风格{data.target}标题"
    if data.content:
        user_msg += f"\n内容摘要：{data.content[:500]}"
    if data.keywords:
        user_msg += f"\n关键词：{', '.join(data.keywords)}"

    input_state = {
        "user_id": u.id, "book_id": None, "chapter_id": None,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": user_msg}],
        "model_choice": mc, "user_memory": user_mem,
        "context": {"count": data.count, "style": data.style, "target": data.target},
        "active_skill": "title-generation", "intent": "assist",
    }
    final = await run_agent(input_state, thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(500, f"标题生成失败：{final.get('error', '未返回内容')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""
    am, cost = await _save_assistant_msg(db, u, thread_id, content, model_id, in_t, out_t, um.id)
    return AssistOut(content=content, model=model_id, in_tokens=in_t, out_tokens=out_t,
                     credits_cost=cost, thread_id=thread_id, message_id=am.id)


assist_title_generation = metered(assist_title_generation)

async def assist_scene_enhance(
    data: SceneEnhanceIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """scene-enhance skill：场景增强。"""
    if not data.scene_text.strip():
        raise HTTPException(400, "场景文本不能为空")
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[场景增强] {data.scene_text[:80]}...")
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)

    input_state = {
        "user_id": u.id, "book_id": None, "chapter_id": None,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": "请增强以下场景"}],
        "model_choice": mc, "user_memory": user_mem,
        "context": {"senses": data.senses, "mood": data.mood, "pov": data.pov,
                    "preserve_length": data.preserve_length},
        "scene_text": data.scene_text,
        "active_skill": "scene-enhance", "intent": "assist",
    }
    final = await run_agent(input_state, thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(500, f"场景增强失败：{final.get('error', '未返回内容')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""
    am, cost = await _save_assistant_msg(db, u, thread_id, content, model_id, in_t, out_t, um.id)
    return AssistOut(content=content, model=model_id, in_tokens=in_t, out_tokens=out_t,
                     credits_cost=cost, thread_id=thread_id, message_id=am.id)


assist_scene_enhance = metered(assist_scene_enhance)

async def assist_dialogue_polish(
    data: DialoguePolishIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """dialogue-polish skill：对话润色。"""
    if not data.dialogue_text.strip():
        raise HTTPException(400, "对话文本不能为空")
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[对话润色] goal={data.goal} {data.dialogue_text[:80]}...")
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)

    input_state = {
        "user_id": u.id, "book_id": None, "chapter_id": None,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": "请润色以下对话"}],
        "model_choice": mc, "user_memory": user_mem,
        "context": {"characters": data.characters, "goal": data.goal, "preserve_info": data.preserve_info},
        "dialogue_text": data.dialogue_text,
        "active_skill": "dialogue-polish", "intent": "assist",
    }
    final = await run_agent(input_state, thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(500, f"对话润色失败：{final.get('error', '未返回内容')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""
    am, cost = await _save_assistant_msg(db, u, thread_id, content, model_id, in_t, out_t, um.id)
    return AssistOut(content=content, model=model_id, in_tokens=in_t, out_tokens=out_t,
                     credits_cost=cost, thread_id=thread_id, message_id=am.id)


assist_dialogue_polish = metered(assist_dialogue_polish)

async def assist_reading_config_gen(
    data: ReadingConfigGenIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """reading-config-gen skill：生成阅读配置JSON。"""
    thread_id = data.thread_id or uuid.uuid4().hex
    um = Message(user_id=u.id, thread_id=thread_id, role="user",
                 content=f"[阅读配置生成] scene={data.scene}")
    db.add(um)
    await db.commit()
    await db.refresh(um)

    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)

    input_state = {
        "user_id": u.id, "book_id": None, "chapter_id": None,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": f"场景：{data.scene}"}],
        "model_choice": mc, "user_memory": user_mem,
        "context": {"scene": data.scene, "user_prefs": data.user_prefs, "book_genre": data.book_genre},
        "active_skill": "reading-config-gen", "intent": "assist",
    }
    final = await run_agent(input_state, thread_id)
    content = final.get("draft_content", "") or ""
    if not content:
        raise HTTPException(500, f"阅读配置生成失败：{final.get('error', '未返回内容')}")
    tu = final.get("token_usage") or {}
    in_t, out_t = int(tu.get("in_tokens", 0)), int(tu.get("out_tokens", 0))
    model_id = tu.get("model_id", "") or ""
    am, cost = await _save_assistant_msg(db, u, thread_id, content, model_id, in_t, out_t, um.id)
    return AssistOut(content=content, model=model_id, in_tokens=in_t, out_tokens=out_t,
                     credits_cost=cost, thread_id=thread_id, message_id=am.id)


assist_reading_config_gen = metered(assist_reading_config_gen)

