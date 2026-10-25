"""Agent 运行时统一入口（供 backend 薄网关调用）。

backend 只做：鉴权 / 计费 / 落库 / SSE 格式；真正的 agent 执行全部走这里。
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from . import graph as graph_mod


def get_graph():
    return graph_mod.graph


def get_outline_graph():
    return graph_mod.outline_graph


def fresh_input(input_state: dict) -> dict:
    """新请求清理上次执行的临时状态；会话消息和持久记忆仍由图管理。"""
    return {"intent": None, "active_skill": None, "draft_content": "", "analysis_report": "",
            "review_round": 0, "review_feedback": "", "token_usage": {}, "error": None, "error_code": None,
            "modify_request": "", "selected_text": "", "prefix_text": "", **input_state}


def checkpoint_key(input_state,thread_id):
    return f"sc:v2:u{input_state.get('user_id',0)}:b{input_state.get('book_id') or 0}:c{input_state.get('chapter_id') or 0}:{thread_id}"

async def _run_graph(input_state: dict, thread_id: str) -> dict:
    """非流式调用 agent，返回最终 state（合并所有节点 diff）。"""
    config = {"configurable": {"thread_id": checkpoint_key(input_state,thread_id)}}
    final: dict = {}
    async for chunk in get_graph().astream(fresh_input(input_state), config=config, stream_mode="updates"):
        for node, diff in (chunk or {}).items():
            if isinstance(diff, dict):
                final.update(diff)
    return final


async def _stream_graph(input_state: dict, thread_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    """流式调用 agent，逐个节点 yield (node_name, state_diff)。"""
    config = {"configurable": {"thread_id": checkpoint_key(input_state,thread_id)}}
    async for chunk in get_graph().astream(fresh_input(input_state), config=config, stream_mode="updates"):
        for node, diff in (chunk or {}).items():
            if isinstance(diff, dict):
                yield node, diff


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_agent(input_state: dict, thread_id: str) -> dict:
    from .agent import StoryClaw
    return await StoryClaw(None).legacy_run(input_state,thread_id)

async def stream_agent(input_state: dict, thread_id: str):
    from .agent import StoryClaw
    async for event in StoryClaw(None).legacy_stream(input_state,thread_id):yield event

async def recover_candidate(thread_id,user_id,book_id,chapter_id):
    """Read verified checkpoints only. New keys isolate user/book/chapter; legacy reads verify values."""
    namespaced=checkpoint_key({'user_id':user_id,'book_id':book_id,'chapter_id':chapter_id},thread_id)
    for key in (namespaced,thread_id):
        count=0
        async for snapshot in get_graph().aget_state_history({'configurable':{'thread_id':key}}):
            count+=1
            if count>30:break
            values=snapshot.values
            if values.get('user_id')!=user_id or values.get('book_id')!=book_id or values.get('chapter_id')!=chapter_id:continue
            content=values.get('draft_content') or ''
            if content.strip():return {'content':content,'thread_id':thread_id}
    return None
