"""Chat 节点：默认对话（注入 skill 索引 + 完整多轮历史 + Skill 自主发现）。

对话时把 describe_skill / read_skill_file 绑定给 LLM，使其能按 <skill_index>
自主发现并加载合适的 skill（DeerFlow 风格）；模型不支持 tools 时降级为普通对话。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from storyclaw.prompts import templates as prompts
from storyclaw.models.calls import usage_payload
from storyclaw.models.llm import get_llm
from storyclaw.agents.state import AgentState
from storyclaw.tools.writing import skill_loop


async def chat_node(state: AgentState) -> dict:
    msgs = state.get("messages") or []
    conv = []
    for m in msgs:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            conv.append(HumanMessage(content=content))
        elif role == "assistant":
            conv.append(AIMessage(content=content))
    if not any(isinstance(m, HumanMessage) for m in conv):
        return {"draft_content": "", "status": "finished"}
    sys_prompt = prompts.build_chat_system(state)
    # Skill 自主发现（模型不支持工具时返回空，走普通对话）
    content, model_id, in_t, out_t = await skill_loop(state, sys_prompt, conv)
    if not content:
        try:
            llm, model_id = await get_llm(state.get("model_choice") or {})
        except Exception as e:
            return {"draft_content": "", "error": f"LLM 构造失败: {e}", "status": "error"}
        try:
            resp = await llm.ainvoke([SystemMessage(content=sys_prompt), *conv])
        except Exception as e:
            return {"draft_content": "", "error": f"Chat LLM 调用失败: {e}", "status": "error"}
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        usage = getattr(resp, "usage_metadata", None) or {}
        in_t = int(usage.get("input_tokens", 0) or 0)
        out_t = int(usage.get("output_tokens", 0) or 0)
    return {
        "draft_content": content,
        "messages": [{"role": "assistant", "content": content}],
        "token_usage": usage_payload(model_id, in_t, out_t),
        "status": "finished",
    }
