"""Writer 节点：首次写作 / 修改 / 段内续写 / 选中文本润色。

- intent=write:     调用 write-chapter skill，从大纲+前章摘要生成
- intent=modify:    调用 modify-chapter skill，基于当前章节内容+修改要求重写
- intent=continue:  调用 continue-writing skill，段内续写片段
- intent=polish:    调用 polish-chapter skill，选中文本润色
"""
from __future__ import annotations

import json
import logging

from storyclaw.prompts import templates as prompts
from storyclaw.models.errors import model_failure
from storyclaw.models.calls import ensure_paragraphs
from storyclaw.models.calls import llm_respond
from storyclaw.models.calls import stream_llm_respond
from storyclaw.models.calls import usage_payload
from storyclaw.runtime.deps import get_deps
from storyclaw.runtime.deps import get_stream_sink
from storyclaw.skills.loader import describe_skill
from storyclaw.skills.loader import read_skill_sections
from storyclaw.skills.loader import method_instructions
from storyclaw.agents.state import AgentState
from storyclaw.tools.writing import tool_loop

log = logging.getLogger("storyclaw.writer")

def _usage(state,model_id,in_t,out_t):
    previous=state.get('token_usage') or {}
    if previous.get('model_id')==model_id:
        in_t+=int(previous.get('in_tokens',0));out_t+=int(previous.get('out_tokens',0))
    return usage_payload(model_id,in_t,out_t)


async def _respond_aware(state: AgentState, sys_prompt: str, user_msg: str):
    """统一应答入口：有流式 sink（SSE 请求）时逐 token 推送，否则非流式；
    无论哪种方式，最终内容都做「空行分段」后处理。"""
    world=((state.get('context') or {}).get('setting_briefs') or {}).get('world')
    if world:sys_prompt+='\n\n【作者世界观与叙事规则】\n'+world
    framework=(state.get('context') or {}).get('framework') or {}
    if framework.get('planning_mode')=='serial':
        from storyclaw.workflows.serial import framework_content
        sys_prompt+='\n\n【长期方向与阶段目标：这是未来计划，不是已发生事实】\n'+json.dumps(framework_content(framework),ensure_ascii=False)[:6000]
    previous=(state.get('context') or {}).get('recent_chapter_text')
    if previous:sys_prompt+='\n\n【上一章原文：已发生的事实，不得把已完成的催缴、交易、发现等重新演一遍】\n'+previous
    sink = get_stream_sink()

    async def on_delta(piece: str):
        await sink("draft", {"delta": piece})

    if sink is not None:
        content, in_t, out_t, model_id = await stream_llm_respond(state, sys_prompt, user_msg, on_delta)
    else:
        content, in_t, out_t, model_id = await llm_respond(state, sys_prompt, user_msg)
    return ensure_paragraphs(content), in_t, out_t, model_id


def _skill_instructions(skill_name: str) -> str:
    return method_instructions(skill_name)


async def writer(state: AgentState) -> dict:
    intent = state.get("intent") or "write"
    if intent == "continue":
        return await _writer_continue(state)
    if intent == "polish":
        return await _writer_polish(state)
    is_modify = intent == "modify" and bool(state.get("modify_request") or state.get("current_content"))
    if is_modify:
        return await _writer_modify(state)
    return await _writer_write(state)


async def _writer_write(state: AgentState) -> dict:
    describe_skill("write-chapter")
    ctx = state.get("context") or {}
    blueprint=ctx.get('blueprint_status') or {}
    if blueprint.get('serial') and not blueprint.get('confirmed'):
        return {'draft_content':'','error':'连载模式请先确认本章章纲；不要求预先规划全书章节','status':'error'}
    memory=ctx.get('memory_status') or {}
    if memory.get('error'):
        return {'draft_content':'','error':'故事记忆检索失败，未生成正文：'+memory['error'],'status':'error'}
    if memory.get('pending_chapters'):
        return {'draft_content':'','error':'请先审阅并更新历史章节故事记忆：'+str(memory['pending_chapters']),'status':'error'}
    chapter_meta = ctx.get("chapter_meta") or {}
    target_words = int(chapter_meta.get("per_chapter_words", 3000) or 3000)
    sb = (ctx.get("setting_briefs") or {})
    # Tool Use 模式：deps 注入了工具执行器时，设定/RAG 不再全量预注入，
    # 让 LLM 通过 query_setting / query_memory 等工具按需查询（省 token、更灵活）。
    use_tools = get_deps().tool_executor is not None
    if use_tools:
        char_briefs = sb.get("characters") or "（暂无角色设定，可调用工具查询）"
        scene_briefs = sb.get("scenes") or "（暂无）"
        item_briefs = sb.get("items") or "（暂无）"
        plot_briefs = sb.get("plots") or "（暂无）"
        rag_briefs = ctx.get("rag_briefs") or "（暂无，可调用工具检索）"
    else:
        char_briefs = sb.get("characters") or "（暂无）"
        scene_briefs = sb.get("scenes") or "（暂无）"
        item_briefs = sb.get("items") or "（暂无）"
        plot_briefs = sb.get("plots") or "（暂无）"
        rag_briefs = ctx.get("rag_briefs") or "（暂无检索结果）"
    sys_prompt = prompts.WRITER_SYSTEM.format(
        chapter_title=chapter_meta.get("title", ""),
        target_words=target_words,
        outline_node=json.dumps(ctx.get("outline_node") or {}, ensure_ascii=False),
        prev_summary=ctx.get("prev_chapter_summary", "（无前章）"),
        character_briefs=char_briefs,
        scene_briefs=scene_briefs,
        item_briefs=item_briefs,
        plot_briefs=plot_briefs,
        rag_briefs=rag_briefs,
        user_prefs=json.dumps(state.get("user_memory") or {}, ensure_ascii=False),
    ) + "\n\n" + _skill_instructions("write-chapter")
    sys_prompt += "\n【作品简介与创作约定】\n" + ctx.get("book_brief", "") + "\n【本章场景任务单】\n" + json.dumps(ctx.get("scene_plan") or {},ensure_ascii=False)
    if state.get("review_feedback") and state.get("draft_content"):
        sys_prompt += "\n【待修订的完整候选：保留已写事件，仅修正审阅问题】\n"+state["draft_content"][:20000]
    if state.get("review_feedback"):
        sys_prompt += "\n【上轮审阅要求】" + state["review_feedback"] + "。返回完整正文，不要说明修改过程。"
    msgs = state.get("messages") or []
    user_msg = msgs[-1]["content"] if msgs else f"请撰写《{chapter_meta.get('title', '')}》"
    # Tool Use：ReAct 收集工具结果（未注入工具时为空，直接生成）
    try:
        tool_out = await tool_loop(state, sys_prompt, user_msg)
        if tool_out:
            sys_prompt += "\n\n【工具查询结果】\n" + tool_out
    except Exception as e:
        return {"draft_content":state.get("draft_content", ""),"status":"error",**model_failure(e)}
    try:
        content, in_t, out_t, model_id = await _respond_aware(state, sys_prompt, user_msg)
    except Exception as e:
        return {"draft_content": state.get("draft_content", ""), "status": "error", **model_failure(e)}
    return {
        "draft_content": content, "active_skill": "write-chapter",
        "token_usage": _usage(state, model_id, in_t, out_t), "error": None,
    }


async def _writer_modify(state: AgentState) -> dict:
    describe_skill("modify-chapter")
    ctx = state.get("context") or {}
    chapter_meta = ctx.get("chapter_meta") or {}
    current = state.get("current_content") or ""
    modify_req = state.get("modify_request") or ""
    sys_prompt = prompts.MODIFY_SYSTEM.format(
        chapter_title=chapter_meta.get("title", ""),
        current_content=current,
        modify_request=modify_req,
        user_prefs=json.dumps(state.get("user_memory") or {}, ensure_ascii=False),
    ) + "\n\n" + _skill_instructions("modify-chapter")
    try:
        content, in_t, out_t, model_id = await _respond_aware(state, sys_prompt, f"请按要求修改本章：{modify_req}")
    except Exception as e:
        return {"draft_content": state.get("draft_content", ""), "status": "error", **model_failure(e)}
    return {
        "draft_content": content, "active_skill": "modify-chapter",
        "token_usage": _usage(state, model_id, in_t, out_t), "error": None,
    }


async def _writer_continue(state: AgentState) -> dict:
    describe_skill("continue-writing")
    ctx = state.get("context") or {}
    chapter_meta = ctx.get("chapter_meta") or {}
    prefix = state.get("prefix_text") or ""
    if not prefix:
        prefix = (state.get("current_content") or "")[-1500:]
    sys_prompt = prompts.CONTINUE_SYSTEM.format(
        chapter_number=chapter_meta.get("number", "?"),
        chapter_title=chapter_meta.get("title", ""),
        outline_node=json.dumps(ctx.get("outline_node") or {}, ensure_ascii=False),
        prefix_text=prefix,
        max_words=int(ctx.get("fragment_max_words", 600)),
        user_prefs=json.dumps(state.get("user_memory") or {}, ensure_ascii=False),
    ) + "\n\n" + _skill_instructions("continue-writing")
    try:
        content, in_t, out_t, model_id = await _respond_aware({**state, "response_max_tokens": max(256, int(ctx.get("fragment_max_words", 600) * 1.6))}, sys_prompt, "请基于上文续写片段，写完一个短场景即停，不展开后续情节")
    except Exception as e:
        return {"draft_content": state.get("draft_content", ""), "status": "error", **model_failure(e)}
    return {
        "draft_content": content, "active_skill": "continue-writing",
        "token_usage": _usage(state, model_id, in_t, out_t), "error": None,
    }


async def _writer_polish(state: AgentState) -> dict:
    describe_skill("polish-chapter")
    selected = state.get("selected_text") or ""
    polish_goal = state.get("polish_goal") or "提升文笔与画面感"
    if not selected:
        return {"draft_content": "", "error": "未提供待润色文本", "status": "error"}
    sys_prompt = prompts.POLISH_SYSTEM.format(
        polish_goal=polish_goal,
        selected_text=selected,
        user_prefs=json.dumps(state.get("user_memory") or {}, ensure_ascii=False),
    ) + "\n\n" + _skill_instructions("polish-chapter")
    try:
        content, in_t, out_t, model_id = await _respond_aware({**state, "response_max_tokens": min(8192, max(512, len(selected) * 2 + 256))}, sys_prompt, "请润色这段文字")
    except Exception as e:
        return {"draft_content": state.get("draft_content", ""), "status": "error", **model_failure(e)}
    return {
        "draft_content": content, "active_skill": "polish-chapter",
        "token_usage": _usage(state, model_id, in_t, out_t), "error": None,
    }
