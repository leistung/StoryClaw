"""Agent 图编排：Supervisor 路由 + Writer/Reviewer/Researcher/Analyst/Assistant/Chat。

- 检查点：优先 deps.checkpointer（PostgresSaver，断点恢复），未注入则 InMemorySaver。
- rebuild_graph(): backend 完成 configure 注入后调用，以生效真实 checkpointer。
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from storyclaw.runtime.deps import get_deps
from storyclaw.agents.nodes import analyst
from storyclaw.agents.nodes import assistant
from storyclaw.agents.nodes import chat_node
from storyclaw.agents.nodes import researcher
from storyclaw.agents.nodes import reviewer
from storyclaw.agents.nodes import supervisor
from storyclaw.agents.nodes import writer
from storyclaw.workflows.outline import plan_outline
from storyclaw.agents.state import AgentState
from storyclaw.agents.state import OutlineState
from storyclaw.utils.tracing import trace_node

# 节点包装缓存：trace 包装只在模块加载时做一次，rebuild_graph() 复用同一包装
_TRACED: dict[str, object] = {}


def _wrapped(name: str, fn) -> object:
    if name not in _TRACED:
        _TRACED[name] = trace_node(name)(fn)
    return _TRACED[name]


def build_outline_graph():
    g = StateGraph(OutlineState)
    g.add_node("plan_outline", plan_outline)
    g.add_edge(START, "plan_outline")
    g.add_edge("plan_outline", END)
    return g.compile()


outline_graph = build_outline_graph()


def _review_router(state: AgentState) -> str:
    if state.get("status") == "review_retry":
        return "writer"
    return END


def _supervisor_router(state: AgentState) -> str:
    return state.get("intent") or "chat"


def _compile_agent(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("supervisor", _wrapped("supervisor", supervisor))
    g.add_node("writer", _wrapped("writer", writer))
    g.add_node("reviewer", _wrapped("reviewer", reviewer))
    g.add_node("researcher", _wrapped("researcher", researcher))
    g.add_node("analyst", _wrapped("analyst", analyst))
    g.add_node("chat", _wrapped("chat", chat_node))
    g.add_node("assistant", _wrapped("assistant", assistant))
    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor", _supervisor_router,
        {
            "write": "writer", "modify": "writer", "continue": "writer", "polish": "writer",
            "analyze": "analyst", "research": "researcher", "review": "reviewer",
            "chat": "chat", "assist": "assistant",
        },
    )
    g.add_edge("writer", "reviewer")
    g.add_conditional_edges("reviewer", _review_router, {"writer": "writer", END: END})
    g.add_edge("researcher", END)
    g.add_edge("analyst", END)
    g.add_edge("chat", END)
    g.add_edge("assistant", END)
    saver = checkpointer or get_deps().checkpointer or InMemorySaver()
    return g.compile(checkpointer=saver)


graph = _compile_agent()


def rebuild_graph():
    """依赖注入（如真实 checkpointer）后重建 agent 图。返回新图。"""
    global graph
    graph = _compile_agent()
    return graph
