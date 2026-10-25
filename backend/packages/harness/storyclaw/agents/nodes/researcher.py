"""Researcher 节点：资料检索（当前为直答；接入 RAG 后查询书籍私有知识库）。"""
from __future__ import annotations

from storyclaw.prompts import templates as prompts
from storyclaw.models.calls import llm_respond
from storyclaw.models.calls import usage_payload
from storyclaw.agents.state import AgentState


async def researcher(state: AgentState) -> dict:
    msgs = state.get("messages") or []
    user_msg = msgs[-1]["content"] if msgs else ""
    try:
        content, in_t, out_t, model_id = await llm_respond(state, prompts.RESEARCHER_SYSTEM, user_msg)
    except Exception as e:
        return {"draft_content": "", "error": f"Researcher LLM 调用失败: {e}", "status": "error"}
    return {
        "draft_content": content,
        "messages": [{"role": "assistant", "content": content}],
        "token_usage": usage_payload(model_id, in_t, out_t),
        "status": "finished",
    }
