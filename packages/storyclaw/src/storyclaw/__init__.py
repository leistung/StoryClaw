"""StoryClaw Agent 包：LangGraph Agent Loop + Tool Use + 向量/图谱 RAG + Skill 系统。

对外统一入口：
- graph / runtime: Agent 执行（stream_agent / run_agent / rebuild_graph）
- rag.service:    章节入库 / 混合检索 / 状态
- skills:         Skill 发现与加载（DeerFlow 风格）
- deps.configure: backend 启动时注入数据层依赖
- llm:            LLM 三格式适配（openai_chat / anthropic / openai_responses）
"""
from __future__ import annotations

from . import deps, graph, llm, memory, prompts, skills
from .checkpointer import build_checkpointer
from .context import build_write_context, count_words, summarize_prev
from .deps import configure, get_deps
from .graph import outline_graph, rebuild_graph
from .llm import build_chat_client, get_llm, set_llm_factory
from .runtime import get_graph, run_agent, sse, stream_agent
from .state import AgentState, OutlineState

# 编译后的 Agent 图（storyclaw.graph 保持为模块；agent_graph 为编译实例）
agent_graph = graph.graph

__all__ = [
    "configure", "get_deps", "deps",
    "graph", "agent_graph", "outline_graph", "rebuild_graph",
    "get_graph", "run_agent", "stream_agent", "sse",
    "build_chat_client", "get_llm", "set_llm_factory", "llm",
    "skills", "memory", "prompts",
    "build_write_context", "count_words", "summarize_prev",
    "build_checkpointer",
    "AgentState", "OutlineState",
]

from .agent import StoryClaw
__all__.append("StoryClaw")
