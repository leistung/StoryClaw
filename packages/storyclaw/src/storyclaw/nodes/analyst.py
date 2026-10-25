"""Analyst 节点：5 个分析 skill 统一入口。

- outline-planning:      大纲规划（复用 outline.plan_outline，JSON 预览）
- plot-planning:         情节节点规划
- character-development: 角色弧光报告
- consistency-check:     一致性检查
- book-summary:          前情提要
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from .. import prompts
from .._util import strip_code_fence
from ..llm import get_llm
from ..outline import plan_outline
from ..skills import read_skill_sections, method_instructions
from ..state import AgentState


def _skill_instructions(skill_name: str) -> str:
    return method_instructions(skill_name)


async def analyst(state: AgentState) -> dict:
    skill = state.get("active_skill") or ""
    ctx = dict(state.get("context") or {})
    ctx["skill_instructions"] = _skill_instructions(skill)
    try:
        llm, model_id = await get_llm(state.get("model_choice") or {})
    except Exception as e:
        return {"analysis_report": "", "error": f"LLM 构造失败: {e}", "status": "error"}

    dispatch = {
        "plot-planning": _analyst_plot,
        "character-development": _analyst_character,
        "consistency-check": _analyst_consistency,
        "book-summary": _analyst_summary,
        "outline-planning": _analyst_outline,
    }
    handler = dispatch.get(skill)
    if not handler:
        return {"analysis_report": "", "error": f"未知分析 skill: {skill}", "status": "error"}

    try:
        report, in_t, out_t = await handler(state, llm, ctx)
    except Exception as e:
        return {"analysis_report": "", "error": f"{skill} 执行失败: {e}", "status": "error"}

    return {
        "analysis_report": report,
        "active_skill": skill,
        "messages": [{"role": "assistant", "content": report[:200] + ("...(报告已生成)" if len(report) > 200 else "")}],
        "token_usage": {"in_tokens": in_t, "out_tokens": out_t, "model_id": model_id},
        "status": "finished",
    }


async def _analyst_outline(state: AgentState, llm, ctx: dict) -> tuple[str, int, int]:
    """大纲规划：复用 outline 子图逻辑，返回 JSON 预览。"""
    book_meta = ctx.get("book_meta") or {}
    try:
        result = await plan_outline({"book_meta": book_meta})
        outline = result.get("outline") or {}
        report = json.dumps(outline, ensure_ascii=False, indent=2)
        if result.get("error"):
            report = f"> ⚠️ {result['error']}\n\n```json\n{report}\n```"
        else:
            report = f"```json\n{report}\n```"
    except Exception as e:
        report = f"大纲生成失败: {e}"
    return report, 0, 0


async def _analyst_plot(state: AgentState, llm, ctx: dict) -> tuple[str, int, int]:
    outline = ctx.get("outline") or {}
    book_meta = ctx.get("book_meta") or {}
    sys_prompt = prompts.ANALYST_PLOT_SYSTEM.format(
        outline=json.dumps(outline, ensure_ascii=False),
        book_meta=json.dumps(book_meta, ensure_ascii=False),
    ) + "\n\n" + (ctx.get("skill_instructions") or "")
    msgs = state.get("messages") or []
    user_msg = msgs[-1]["content"] if msgs else "请规划情节节点"
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    report = strip_code_fence(content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return report, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


async def _analyst_character(state: AgentState, llm, ctx: dict) -> tuple[str, int, int]:
    book_meta = ctx.get("book_meta") or {}
    msgs = state.get("messages") or []
    last = msgs[-1]["content"] if msgs else ""
    character_name = ctx.get("character_name") or ""
    if not character_name:
        m = re.search(r"角色[弧光分析]*(.{1,20})", last)
        character_name = m.group(1).strip() if m else "主角"
    character_intro = ctx.get("character_intro") or book_meta.get("protagonist_intro", "")
    if character_name == book_meta.get("protagonist_name", ""):
        character_intro = character_intro or book_meta.get("protagonist_intro", "")

    outline_brief = json.dumps(ctx.get("outline") or {}, ensure_ascii=False)[:1000]
    sys_prompt = prompts.ANALYST_CHARACTER_SYSTEM.format(
        character_name=character_name,
        character_intro=character_intro or "（未提供）",
        outline_brief=outline_brief,
        book_meta=json.dumps(book_meta, ensure_ascii=False),
    ) + "\n\n" + (ctx.get("skill_instructions") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt),
                              HumanMessage(content=f"请为 {character_name} 生成角色弧光报告")])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return content, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


async def _analyst_consistency(state: AgentState, llm, ctx: dict) -> tuple[str, int, int]:
    cr = state.get("chapter_range") or ctx.get("chapter_range") or {"start": 1, "end": 10}
    start, end = int(cr.get("start", 1)), int(cr.get("end", 10))
    chapters_brief = ctx.get("chapters_brief") or "（未提供章节内容，请通过 backend 注入）"
    outline_brief = json.dumps(ctx.get("outline") or {}, ensure_ascii=False)[:1000]
    sys_prompt = prompts.ANALYST_CONSISTENCY_SYSTEM.format(
        start=start, end=end,
        chapters_brief=chapters_brief,
        outline_brief=outline_brief,
    ) + "\n\n" + (ctx.get("skill_instructions") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt),
                              HumanMessage(content=f"请检查第{start}-{end}章一致性")])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    report = strip_code_fence(content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return report, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


async def _analyst_summary(state: AgentState, llm, ctx: dict) -> tuple[str, int, int]:
    cr = state.get("chapter_range") or ctx.get("chapter_range") or {"start": 1, "end": 10}
    start, end = int(cr.get("start", 1)), int(cr.get("end", 10))
    chapters_brief = ctx.get("chapters_brief") or "（未提供章节内容，请通过 backend 注入）"
    sys_prompt = prompts.ANALYST_SUMMARY_SYSTEM.format(
        start=start, end=end,
        chapters_brief=chapters_brief,
    ) + "\n\n" + (ctx.get("skill_instructions") or "")
    resp = await llm.ainvoke([SystemMessage(content=sys_prompt),
                              HumanMessage(content=f"请生成第{start}-{end}章前情提要")])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    report = strip_code_fence(content)
    usage = getattr(resp, "usage_metadata", None) or {}
    return report, int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)
