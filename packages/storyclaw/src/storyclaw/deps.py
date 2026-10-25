"""依赖注入：backend 在启动时把数据层实现注入到 agent 包内。

这样 packages/storyclaw 保持与业务 DB / 鉴权 / 计费解耦，只依赖注入的契约：
- llm_factory:        async (model_choice: dict) -> (chat_model, model_id)
- load_memory:        async (user_id: int) -> dict
- save_memory:        async (user_id: int, key: str, value) -> None
- load_context:       async (db, user_id: int, book_id: int, chapter_id: int) -> context dict
- embedding_resolver: async () -> embedding cfg dict | None（DB 优先解析）
- context_limit_resolver: (model_choice: dict) -> int | None（模型上下文窗口，可选）
- rag:                实现 rag 服务协议的适配器（可空，rag/service 自管存储）
- checkpointer:       langgraph BaseCheckpointSaver（断点恢复）
- tool_executor:      async (name: str, args: dict, user_id: int, book_id: int, chapter_id: int|None) -> str
                      写作 Tool Use 的实时工具执行器（backend 实现，查库/RAG）
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

# 流式推送通道：backend 在 SSE 请求内 set 一个 async 回调，
# agent 节点（如 writer）把 token/事件增量推给前端。
StreamSink = Callable[[str, dict], Awaitable[None]]
_stream_sink_var: ContextVar[Optional[StreamSink]] = ContextVar("stream_sink", default=None)


def set_stream_sink(sink: Optional[StreamSink]) -> None:
    _stream_sink_var.set(sink)


def get_stream_sink() -> Optional[StreamSink]:
    return _stream_sink_var.get()


@dataclass
class StoryClawDeps:
    llm_factory: Optional[Callable[[dict], Awaitable[tuple]]] = None
    load_memory: Optional[Callable[[int], Awaitable[dict]]] = None
    save_memory: Optional[Callable[[int, str, Any], Awaitable[None]]] = None
    load_context: Optional[Callable[[Any, int, int, int], Awaitable[dict]]] = None
    embedding_resolver: Optional[Callable[[], Awaitable[dict | None]]] = None
    context_limit_resolver: Optional[Callable[[dict], int | None]] = None
    index_resolver: Any = None
    rag: Any = None
    checkpointer: Any = None
    tool_executor: Optional[Callable[[str, dict, int, int, int | None], Awaitable[str]]] = None


_deps = StoryClawDeps()


def configure(**kwargs: Any) -> StoryClawDeps:
    """backend 启动时注入依赖（只覆盖非 None 字段）。返回当前 deps。"""
    for k, v in kwargs.items():
        if v is not None and hasattr(_deps, k):
            setattr(_deps, k, v)
    return _deps


def get_deps() -> StoryClawDeps:
    return _deps
