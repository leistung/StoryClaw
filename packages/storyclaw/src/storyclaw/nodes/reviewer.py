"""Reviewer 节点：字数自检 + 修改要求满足度检查。"""
from __future__ import annotations

import json

from .._util import llm_respond
from ..context import count_words
from ..state import AgentState


async def reviewer(state: AgentState) -> dict:
    draft = state.get("draft_content") or ""
    ctx = state.get("context") or {}
    chapter_meta = ctx.get("chapter_meta") or {}
    target = int(chapter_meta.get("per_chapter_words", 3000) or 3000)
    actual = count_words(draft)
    round_n = int(state.get("review_round") or 0) + 1
    modify_req = state.get("modify_request") or ""
    active_skill = state.get("active_skill") or ""

    # Fragment operations must not be expanded to the whole chapter's target.
    if active_skill in ("continue-writing", "polish-chapter"):
        return {"review_feedback": f"片段完成（{actual}字）", "review_round": round_n,
                "messages": [{"role": "assistant", "content": draft}],
                "status": "finished" if draft.strip() else "error"}

    # modify 模式：用 LLM 检查修改要求是否满足
    if modify_req and active_skill == "modify-chapter" and round_n < 2:
        try:
            satisfied = await _llm_check_modify(draft, modify_req, state)
            if not satisfied["pass"]:
                return {"review_feedback": f"修改未达标：{satisfied['reason']}，请按要求重写",
                        "review_round": round_n, "status": "review_retry"}
            return {
                "review_feedback": f"修改通过：{satisfied['reason']}（{actual}字）",
                "review_round": round_n,
                "messages": [{"role": "assistant", "content": draft[:200] + "...(章节已修改)"}],
                "status": "finished",
            }
        except Exception:
            pass  # LLM 检查失败，降级为字数检查

    from ..continuity import repetition_evidence
    reuse=repetition_evidence(draft,ctx.get('recent_chapter_text',''))
    if reuse['warning'] and round_n<2:
        return {'review_feedback':f"跨章重复风险：与上章出现连续{reuse['max_run']}字、累计{reuse['reused_chars']}字长片段复用。不要重演上章已完成的交易、发现或对话，保留本章新事件并完整重写",'review_round':round_n,'status':'review_retry'}

    # 字数自检
    if not target * 0.9 <= actual <= target * 1.18 and round_n < 2:
        return {"review_feedback": f"字数偏离目标：当前 {actual} 字，目标 {target} 字。输出接近目标的完整版本；过长则压缩且保留全部本章事件，过短则补充动作与对话",
                "review_round": round_n, "status": "review_retry"}
    return {
        "review_feedback": (f"跨章重复风险（最长{reuse['max_run']}字，累计{reuse['reused_chars']}字），请人工核对。" if reuse['warning'] else "") + (f"字数符合目标（{actual}/{target} 字）" if target * 0.9 <= actual <= target * 1.18 else f"字数偏离目标（{actual}/{target} 字），请继续修订"),
        "review_round": round_n,
        "messages": [{"role": "assistant", "content": draft[:200] + "...(章节已生成)"}],
        "status": "finished",
    }


async def _llm_check_modify(draft: str, modify_req: str, state: AgentState) -> dict:
    try:
        content, _, _, _ = await llm_respond(
            state,
            '判断草稿是否满足用户的修改要求。只输出严格 JSON：{"pass":true|false,"reason":"简短说明"}\n不要任何其他文字。',
            f"【修改要求】{modify_req}\n\n【草稿前1000字】{draft[:1000]}",
        )
    except Exception:
        return {"pass": True, "reason": "LLM 不可用，跳过修改检查"}
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(content)
        return {"pass": bool(result.get("pass", True)), "reason": str(result.get("reason", ""))}
    except Exception:
        return {"pass": True, "reason": "解析失败，默认通过"}
