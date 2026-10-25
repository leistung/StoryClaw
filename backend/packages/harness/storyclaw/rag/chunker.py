"""文本切片器：先按段落，超长按固定长度+重叠（从 backend 迁移，纯函数无外部依赖）。"""
from __future__ import annotations

import re
from typing import Any

MAX_LEN = 512
OVERLAP = 64


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paras if p.strip()]


def _split_long(text: str, max_len: int = MAX_LEN, overlap: int = OVERLAP) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    i = 0
    while i < len(text):
        end = i + max_len
        chunks.append(text[i:end])
        if end >= len(text):
            break
        i = end - overlap
    return chunks


def chunk_text(
    text: str,
    chapter_id: int,
    volume_id: int | None = None,
) -> list[dict[str, Any]]:
    """章节文本切片，返回 [{chunk_idx, text, metadata_json}] 列表。"""
    clean = _strip_html(text)
    if not clean:
        return []
    paras = _split_paragraphs(clean)
    chunks: list[dict[str, Any]] = []
    idx = 0
    for para in paras:
        pieces = _split_long(para)
        for piece in pieces:
            chunks.append({
                "chunk_idx": idx,
                "text": piece,
                "metadata_json": {
                    "chapter_id": chapter_id,
                    "volume_id": volume_id,
                    "char_len": len(piece),
                },
            })
            idx += 1
    return chunks
