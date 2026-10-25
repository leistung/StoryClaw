"""内存降级存储：Milvus / Neo4j 不可用时使用（开发 / 无 infra 环境）。

仅用于保证应用可运行；重启即丢失，生产请接入 Milvus + Neo4j。
"""
from __future__ import annotations

from typing import Any

from storyclaw.rag.embedding import cosine_similarity


class MemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self._graphs: dict[tuple[int, int], dict[str, Any]] = {}

    # ---- chunks ----
    def upsert(self, user_id: int, book_id: int, rows: list[dict]) -> int:
        key = (user_id, book_id)
        self._chunks.setdefault(key, []).extend(rows)
        return len(rows)

    def delete_chapter(self, user_id: int, book_id: int, chapter_id: int) -> None:
        key = (user_id, book_id)
        if key in self._chunks:
            self._chunks[key] = [c for c in self._chunks[key] if c["chapter_id"] != chapter_id]

    def search(self, user_id: int, book_id: int, query_vec: list[float], top_k: int, allowed_chapter_ids: list[int] | None = None) -> list[dict]:
        rows = self._chunks.get((user_id, book_id), [])
        if allowed_chapter_ids is not None:
            allowed=set(allowed_chapter_ids);rows=[c for c in rows if c["chapter_id"] in allowed]
        scored = [(cosine_similarity(query_vec, c.get("embedding") or []), c) for c in rows]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "chapter_id": c["chapter_id"],
                "volume_id": c.get("volume_id"),
                "chunk_idx": c.get("chunk_idx"),
                "text": c.get("text", ""),
                "score": round(s, 4),
            }
            for s, c in scored[:top_k]
        ]

    def count_chunks(self, user_id: int, book_id: int, chapter_id: int | None = None) -> int:
        rows = self._chunks.get((user_id, book_id), [])
        if chapter_id is None:
            return len(rows)
        return sum(1 for c in rows if c["chapter_id"] == chapter_id)

    # ---- graph ----
    def upsert_graph(self, user_id: int, book_id: int, chapter_id: int,
                     entities: list[dict], relations: list[dict]) -> None:
        key = (user_id, book_id)
        g = self._graphs.setdefault(key, {"entities": [], "relations": []})
        # 移除该章节旧实体，再合并新实体（按 name 去重）
        g["entities"] = [e for e in g["entities"] if e.get("chapter_id") != chapter_id]
        for e in entities:
            e = {**e, "chapter_id": chapter_id}
            existing = next((x for x in g["entities"] if x["name"] == e.get("name")), None)
            if existing:
                existing.update({k: v for k, v in e.items() if v})
            else:
                g["entities"].append(e)
        g["relations"] = [r for r in g["relations"] if r.get("chapter_id") != chapter_id]
        for r in relations:
            g["relations"].append({**r, "chapter_id": chapter_id})

    def query_related(self, user_id: int, book_id: int, query_text: str, limit: int = 8, allowed_chapter_ids: list[int] | None = None) -> dict:
        g = self._graphs.get((user_id, book_id), {"entities": [], "relations": []})
        allowed=set(allowed_chapter_ids) if allowed_chapter_ids is not None else None
        ents = [e for e in g["entities"] if (allowed is None or e.get("chapter_id") in allowed)
                and (query_text in (e.get("name") or "") or query_text in (e.get("description") or ""))]
        ents = ents[:limit]
        names = {e.get("name") for e in ents}
        rels = [r for r in g["relations"] if (r.get("from") in names or r.get("to") in names) and (allowed is None or r.get("chapter_id") in allowed)]
        return {"entities": ents, "relations": rels[:50]}

    def book_graph(self, user_id: int, book_id: int) -> dict:
        g = self._graphs.get((user_id, book_id), {"entities": [], "relations": []})
        return {"entities": g["entities"], "relations": g["relations"]}

    def related_to_name(self, user_id: int, book_id: int, name: str, limit: int = 20) -> dict:
        g = self._graphs.get((user_id, book_id), {"entities": [], "relations": []})
        ents = [e for e in g["entities"] if name in (e.get("name") or "")]
        ents = ents[:limit]
        names = {e.get("name") for e in ents}
        rels = [r for r in g["relations"] if r.get("from") in names or r.get("to") in names]
        return {"entities": ents, "relations": rels[:50]}

    def count_entities(self, user_id: int, book_id: int, chapter_id: int | None = None) -> int:
        g = self._graphs.get((user_id, book_id), {"entities": []})
        if chapter_id is None:
            return len(g["entities"])
        return sum(1 for e in g["entities"] if e.get("chapter_id") == chapter_id)
