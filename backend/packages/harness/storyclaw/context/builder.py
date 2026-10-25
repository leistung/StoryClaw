"""写作上下文：Agent 需要的大纲节点 / 前章摘要 / 章节元数据。

- 纯工具（字数统计 / 摘要 / 大纲定位）放本模块，供 backend 数据层复用；
- `build_write_context` 委托给 backend 注入的 load_context（数据层实现）。
"""
from __future__ import annotations

import re
from typing import Any

from storyclaw.runtime.deps import get_deps


def count_words(text: str) -> int:
    """去除 HTML 标签后的中文字数。"""
    if not text:
        return 0
    text = re.sub(r"<[^>]+>", "", text)
    return len(re.sub(r"\s+", "", text))


def summarize_prev(prev_content: str, max_chars: int = 600) -> str:
    """前章摘要：去 HTML + 截断（P0-5 接入 RAG 后可换 LLM 摘要）。"""
    if not prev_content:
        return ""
    text = re.sub(r"<[^>]+>", "", prev_content)
    text = re.sub(r"\s+", "", text)
    return text[-max_chars:] if len(text) > max_chars else text


def find_outline_node(outline_content: dict, chapter_number: int) -> dict[str, Any]:
    """从大纲 JSON 中按章节序号定位节点。"""
    for vol in outline_content.get("volumes", []) or []:
        for ch in vol.get("chapters", []) or []:
            if int(ch.get("number", 0)) == chapter_number:
                return ch
    return {}


async def build_write_context(db: Any, user_id: int, book_id: int, chapter_id: int) -> dict[str, Any]:
    """构造 write-chapter skill 的 context 字典（委托 backend 数据层）。

    db 为不透明对象（SQLAlchemy AsyncSession），由 backend 实现消费。
    """
    loader = get_deps().load_context
    if loader is None:
        return {}
    return await loader(db, user_id, book_id, chapter_id)
