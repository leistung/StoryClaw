"""长期记忆（Memory Manager）：用户写作偏好。

- 数据读写由 backend 注入（deps.load_memory / save_memory，走 PG user_memories 表）；
- 本模块提供默认偏好、编解码等纯工具，供 backend 实现与 prompt 构造复用。
"""
from __future__ import annotations

import json
from typing import Any

DEFAULT_PREFS: dict[str, Any] = {
    "tone": "花火风格，悲情基调",
    "pov": "第三人称",
    "custom": {},
}


def default_memory() -> dict[str, Any]:
    return dict(DEFAULT_PREFS)


def merge_memory(rows: dict[str, Any]) -> dict[str, Any]:
    """合并 DB 读取结果与默认偏好，返回可直接放入 AgentState.user_memory 的 dict。"""
    prefs: dict[str, Any] = dict(DEFAULT_PREFS)
    prefs.update({k: v for k, v in (rows or {}).items() if v is not None})
    return prefs


def encode(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def decode(raw: str) -> Any:
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except Exception:
        return raw
