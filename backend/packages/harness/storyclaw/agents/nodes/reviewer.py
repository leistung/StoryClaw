"""Reviewer 节点：字数自检 + 修改要求满足度检查。"""
from __future__ import annotations

import json

from storyclaw.models.calls import llm_respond
from storyclaw.context.builder import count_words
from storyclaw.agents.state import AgentState


async def reviewer(state: AgentState) -> dict:
    if state.get("error") or state.get("status")=="error":
        return {"status":"error","review_feedback":"生成或修订已中断；已有候选不等于审阅通过。"}
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
            if satisfied.get("unknown"):
                return {"status":"error","error":"修订审阅结果不可用，请人工核对候选。","error_code":"review_unavailable"}
            if not satisfied["pass"]:
                return {"review_feedback": f"修改未达标：{satisfied['reason']}，请按要求重写",
                        "review_round": round_n, "status": "review_retry"}
            return {
                "review_feedback": f"修改通过：{satisfied['reason']}（{actual}字）",
                "review_round": round_n,
                "messages": [{"role": "assistant", "content": draft[:200] + "...(章节已修改)"}],
                "status": "finished",
            }
        except Exception as exc:
            from storyclaw.models.errors import model_failure
            return {"status":"error",**model_failure(exc)}

    from storyclaw.workflows.continuity import repetition_evidence
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
        raise
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(content)
        return {"pass": bool(result.get("pass", True)), "reason": str(result.get("reason", ""))}
    except Exception:
        return {"pass":False,"unknown":True,"reason":"审阅格式不可用，不能默认通过"}
