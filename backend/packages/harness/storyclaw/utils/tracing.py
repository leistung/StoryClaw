"""Agent 节点可观测性：为每个 LangGraph 节点记录耗时 / 意图 / token 用量 / 状态。

用法：graph.py 中用 trace_node("writer")(writer) 包装节点函数。
自动识别同步/异步节点：同步节点用同步包装，异步节点用异步包装，
避免对同步函数 `await` 其返回值导致 TypeError。

日志走 storyclaw.agent logger（logfmt 格式，与请求日志一致）。

示例输出：
    2026-08-26 10:12:00 INFO storyclaw.agent node=writer duration_ms=4123 intent=write status=running in_tokens=1200 out_tokens=800 msg=node
"""

from __future__ import annotations

import inspect
import logging
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("storyclaw.agents.lead_agent.agent")


def _emit(name: str, start: float, state: dict[str, Any], out: Any) -> Any:
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    data: dict[str, Any] = {
        "node": name,
        "duration_ms": duration_ms,
        "intent": state.get("intent"),
        "status": out.get("status") if isinstance(out, dict) else None,
    }
    if isinstance(out, dict):
        tu = out.get("token_usage")
        if isinstance(tu, dict):
            data["in_tokens"] = tu.get("in_tokens")
            data["out_tokens"] = tu.get("out_tokens")
    logger.info("node", extra={"data": data})
    return out


def _error(name: str, e: Exception) -> None:
    logger.error("node_error", extra={"data": {"node": name, "error": str(e)[:200]}})


def trace_node(name: str) -> Callable:
    """包装节点函数（自动适配同步/异步）。"""

    def deco(fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def wrapper(state: dict[str, Any]):
                from storyclaw.runtime.progress import progress
                await progress('step.started',name,label={'writer':'生成或修订正文','reviewer':'检查字数、重复与修订要求'}.get(name,name))
                start = time.perf_counter()
                try:
                    out = await fn(state)
                except Exception as e:
                    _error(name, e)
                    await progress('step.failed',name,error=str(e)[:600])
                    raise
                await progress('step.failed' if out.get('error') or out.get('status')=='error' else 'step.completed',name,duration_ms=round((time.perf_counter()-start)*1000),
                               status=out.get('status'),review_feedback=out.get('review_feedback'),error=out.get('error'))
                return _emit(name, start, state, out)
        else:
            @wraps(fn)
            def wrapper(state: dict[str, Any]):
                start = time.perf_counter()
                try:
                    out = fn(state)
                except Exception as e:
                    _error(name, e)
                    raise
                return _emit(name, start, state, out)
        return wrapper

    return deco
