"""Assistant 节点：5 个辅助 skill 统一入口。

- brainstorm:        头脑风暴
- title-generation:  标题生成
- scene-enhance:     场景增强
- dialogue-polish:   对话润色
- reading-config-gen:阅读配置生成
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from .. import prompts
from .._util import strip_code_fence
from ..llm import get_llm
from ..skills import method_instructions
from ..state import AgentState


async def assistant(state: AgentState) -> dict:
    skill = state.get("active_skill") or ""
    try:
        llm, model_id = await get_llm(state.get("model_choice") or {})
    except Exception as e:
        return {"draft_content": "", "error": f"LLM 构造失败: {e}", "status": "error"}

    dispatch = {
        "brainstorm": _assist_brainstorm,
        "title-generation": _assist_title,
        "scene-enhance": _assist_scene,
        "dialogue-polish": _assist_dialogue,
        "reading-config-gen": _assist_reading_config,
    }
    handler = dispatch.get(skill)
    if not handler:
        return {"draft_content": "", "error": f"未知辅助 skill: {skill}", "status": "error"}

    try:
        content, in_t, out_t = await handler(state, llm)
    except Exception as e:
        return {"draft_content": "", "error": f"{skill} 执行失败: {e}", "status": "error"}

    return {
        "draft_content": content,
        "active_skill": skill,
        "messages": [{"role": "assistant", "content": content[:200] + ("..." if len(content) > 200 else "")}],
        "token_usage": {"in_tokens": in_t, "out_tokens": out_t, "model_id": model_id},
        "status": "finished",
    }


async def _assist_brainstorm(state: AgentState, llm) -> tuple[str, int, int]:
    ctx = state.get("context") or {}
    msgs = state.get("messages") or []
    user_msg = msgs[-1]["content"] if msgs else "请提供创意建议"
    count = int(ctx.get("count", 8))
    sys_prompt = prompts.ASSIST_BRAINSTORM_SYSTEM.format(count=count)
    book_meta = ctx.get("book_meta") or {}
    if book_meta:
        sys_prompt += f"\n书籍：《{book_meta.get('title','')}》{book_meta.get('genre','')}主角：{book_meta.get('protagonist_name','')}"
    sys_prompt += "\n\n" + method_instructions(state.get("active_skill") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return content, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


async def _assist_title(state: AgentState, llm) -> tuple[str, int, int]:
    ctx = state.get("context") or {}
    msgs = state.get("messages") or []
    user_msg = msgs[-1]["content"] if msgs else "请生成标题"
    count = int(ctx.get("count", 6))
    style = ctx.get("style", "classic")
    target = ctx.get("target", "chapter")
    sys_prompt = prompts.ASSIST_TITLE_SYSTEM.format(count=count, style=style, target=target)
    sys_prompt += "\n\n" + method_instructions(state.get("active_skill") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return content, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


async def _assist_scene(state: AgentState, llm) -> tuple[str, int, int]:
    ctx = state.get("context") or {}
    scene_text = state.get("scene_text") or ctx.get("scene_text") or ""
    msgs = state.get("messages") or []
    user_msg = msgs[-1]["content"] if msgs else scene_text
    mood = ctx.get("mood", "沉浸")
    senses = ctx.get("senses", ["视觉", "听觉"])
    preserve = ctx.get("preserve_length", False)
    length_hint = "保持原文长度，替换式润色" if preserve else "可适当扩写，增量不超过原文2倍"
    sys_prompt = prompts.ASSIST_SCENE_SYSTEM.format(mood=mood, senses="、".join(senses), length_hint=length_hint)
    if scene_text:
        user_msg = f"原文：\n{scene_text}\n\n请增强以上场景。"
    sys_prompt += "\n\n" + method_instructions(state.get("active_skill") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return content, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


async def _assist_dialogue(state: AgentState, llm) -> tuple[str, int, int]:
    ctx = state.get("context") or {}
    dialogue_text = state.get("dialogue_text") or ctx.get("dialogue_text") or ""
    msgs = state.get("messages") or []
    user_msg = msgs[-1]["content"] if msgs else dialogue_text
    goal = ctx.get("goal", "personalize")
    goal_map = {"personalize": "强化角色语言风格区分度", "conflict": "增强对话冲突与张力",
                "info_dense": "提升信息密度", "subtext": "增加潜台词与言外之意"}
    goal_desc = goal_map.get(goal, goal_map["personalize"])
    characters = ctx.get("characters") or []
    chars_info = ""
    if characters:
        parts = [f"{c.get('name','')}({c.get('personality','')}/{c.get('speech_style','')})" for c in characters]
        chars_info = "、".join(parts)
    sys_prompt = prompts.ASSIST_DIALOGUE_SYSTEM.format(goal_desc=goal_desc, characters_info=chars_info or "无角色档案")
    if dialogue_text:
        user_msg = f"原对话：\n{dialogue_text}\n\n请润色以上对话。"
    sys_prompt += "\n\n" + method_instructions(state.get("active_skill") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return content, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


async def _assist_reading_config(state: AgentState, llm) -> tuple[str, int, int]:
    ctx = state.get("context") or {}
    scene = ctx.get("scene", "default")
    sys_prompt = prompts.ASSIST_READING_CONFIG_SYSTEM.format(scene=scene)
    user_prefs = ctx.get("user_prefs") or {}
    user_msg = f"场景：{scene}"
    if user_prefs:
        user_msg += f"\n用户偏好：{json.dumps(user_prefs, ensure_ascii=False)}"
    sys_prompt += "\n\n" + method_instructions(state.get("active_skill") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    content = strip_code_fence(content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return content, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)
