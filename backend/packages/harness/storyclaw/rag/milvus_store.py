"""Milvus 向量存储：章节切片入库/检索（collection 按 user_book 隔离）。"""
from __future__ import annotations

import logging
from typing import Any

from storyclaw.config.settings import settings

log = logging.getLogger("storyclaw.rag.milvus")

try:
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
    _HAS_MILVUS = True
except Exception as e:  # pragma: no cover
    _HAS_MILVUS = False
    log.warning("pymilvus 导入失败（Milvus 不可用）: %s", e)
    Collection = CollectionSchema = DataType = FieldSchema = connections = utility = None


class MilvusStore:
    """封装 pymilvus，提供按 (user_id, book_id) 隔离的 collection 操作。

    任何连接/操作失败都返回空结果并打日志，由 service 层降级到内存存储。
    """

    def __init__(self) -> None:
        self._connected = False
        self._collections: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        if not _HAS_MILVUS:
            return False
        if self._connected:
            return True
        try:
            if settings.milvus_uri:
                connections.connect(uri=settings.milvus_uri)
            else:
                connections.connect(host=settings.milvus_host, port=settings.milvus_port)
            self._connected = True
            return True
        except Exception as e:
            log.warning("Milvus 连接失败（将降级内存存储）: %s", e)
            self._connected = False
            return False

    def _collection_name(self, user_id: int, book_id: int) -> str:
        return f"chunks_u{user_id}_b{book_id}"

    def _ensure_collection(self, user_id: int, book_id: int):
        if not self.connect():
            return None
        name = self._collection_name(user_id, book_id)
        if name in self._collections:
            return self._collections[name]
        try:
            if utility.has_collection(name):
                col = Collection(name)
                # 已存在的 collection 需 load 后才可检索（重启后也要）
                try:
                    col.load()
                except Exception:
                    pass
            else:
                fields = [
                    FieldSchema("id", DataType.INT64, is_primary=True, auto_id=False),
                    FieldSchema("chapter_id", DataType.INT64),
                    FieldSchema("volume_id", DataType.INT64),
                    FieldSchema("chunk_idx", DataType.INT64),
                    FieldSchema("text", DataType.VARCHAR, max_length=4096),
                    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=settings.milvus_dim),
                ]
                schema = CollectionSchema(fields, description="StoryClaw chapter chunks")
                col = Collection(name, schema)
                col.create_index("embedding", {
                    "index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 128},
                })
                col.load()
            self._collections[name] = col
            return col
        except Exception as e:
            log.warning("Milvus collection 创建失败: %s", e)
            return None

    def upsert(self, user_id: int, book_id: int, rows: list[dict]) -> int:
        col = self._ensure_collection(user_id, book_id)
        if col is None:
            return 0
        try:
            col.insert(rows)
            col.flush()
            return len(rows)
        except Exception as e:
            log.warning("Milvus insert 失败: %s", e)
            return 0

    def delete_chapter(self, user_id: int, book_id: int, chapter_id: int) -> None:
        col = self._ensure_collection(user_id, book_id)
        if col is None:
            return
        try:
            col.delete(f"chapter_id == {int(chapter_id)}")
            col.flush()
        except Exception as e:
            log.warning("Milvus delete 失败: %s", e)

    def search(self, user_id: int, book_id: int, query_vec: list[float], top_k: int, allowed_chapter_ids: list[int] | None = None) -> list[dict]:
        col = self._ensure_collection(user_id, book_id)
        if col is None:
            raise RuntimeError('Milvus 检索集合不可用')
        try:
            res = col.search(
                [query_vec], "embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": 16}},
                limit=top_k,
                output_fields=["chapter_id", "volume_id", "chunk_idx", "text"],
                expr=("chapter_id in ["+",".join(str(int(x)) for x in allowed_chapter_ids)+"]") if allowed_chapter_ids is not None else None,
            )
            hits = res[0] if res else []
            out = []
            for h in hits:
                ent = h.entity
                # 注意：本版本 pymilvus 的 Entity.get() 不接受默认值参数
                out.append({
                    "chapter_id": int(ent.get("chapter_id")),
                    "volume_id": ent.get("volume_id"),
                    "chunk_idx": int(ent.get("chunk_idx")),
                    "text": ent.get("text") or "",
                    "score": round(float(h.distance), 4),
                })
            return out
        except Exception as e:
            log.warning("Milvus search 失败: %s", e)
            raise RuntimeError('Milvus 检索失败') from e

    def count_chunks(self, user_id: int, book_id: int, chapter_id: int | None = None) -> int:
        col = self._ensure_collection(user_id, book_id)
        if col is None:
            return 0
        try:
            if chapter_id is None:
                expr = None
            else:
                expr = f"chapter_id == {int(chapter_id)}"
            rows = col.query(expr=expr, output_fields=["count(*)"]) if expr else []
            return int(rows[0].get("count(*)", 0)) if rows else 0
        except Exception:
            return 0

    def delete_chapter_strict(self,user_id,book_id,chapter_id):
        if not self.connect():raise RuntimeError('Milvus unavailable for cleanup')
        name=self._collection_name(user_id,book_id)
        if not utility.has_collection(name):return
        col=self._ensure_collection(user_id,book_id)
        if col is None:raise RuntimeError('Milvus collection unavailable for cleanup')
        col.delete(f'chapter_id == {int(chapter_id)}');col.flush()
