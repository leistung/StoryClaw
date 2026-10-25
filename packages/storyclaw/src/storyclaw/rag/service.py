"""RAG 服务：章节入库 / 检索 / 状态（Milvus 向量 + Neo4j 图谱，缺服务时内存降级）。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from .._util import strip_code_fence
from ..llm import get_llm
from . import chunker, embedding
from .memory_store import MemoryVectorStore
from .milvus_store import MilvusStore
from .neo4j_store import Neo4jStore

log = logging.getLogger("storyclaw.rag")

_milvus = MilvusStore()
_neo4j = Neo4jStore()
_mem = MemoryVectorStore()

ENTITY_EXTRACT_SYSTEM = """你是小说实体抽取器。从给定章节文本中抽取实体与关系。
只输出严格 JSON，格式：
{"entities":[{"name":"实体名","type":"character|scene|item|plot|hook","description":"一句话描述"}],
 "relations":[{"from":"实体A","to":"实体B","type":"关系类型(如: 是_父亲/在_场景/持有/提到)"}]}
要求：
- entities 只保留有辨识度、对后续剧情有用的实体（人物、重要场景、关键物品、伏笔、情节钩子）
- 人物默认 type=character，场景 type=scene，物品 type=item，伏笔 type=hook
- relations 必须在 entities 之间，from/to 与实体 name 完全一致
- 最多12个实体、18条关系，每条描述控制在30字内
- 不要输出任何其他文字"""


def _store_flags() -> dict:
    return {"vector": "milvus" if _milvus.available else ("memory" if _HAS_MEM else "none"),
            "graph": "neo4j" if _neo4j.available else ("memory" if _HAS_MEM else "none")}


_HAS_MEM = os.getenv("RAG_ALLOW_MEMORY_FALLBACK", "false").lower() == "true"


async def _resolve_embed_cfg() -> dict | None:
    """优先 backend 注入的 resolver（可查 DB），否则 None（embedding 内部走 env）。"""
    from ..deps import get_deps
    resolver = get_deps().embedding_resolver
    if resolver is not None:
        try:
            return await resolver()
        except Exception:
            return None
    return None


async def ingest_text(
    user_id: int, book_id: int, chapter_id: int, volume_id: int | None,
    content: str, model_choice: dict | None = None, extract_entities: bool = True,
) -> dict:
    """章节入库：切片 → 向量入库（Milvus/内存） + 实体图谱（Neo4j/内存）。

    Returns {"chunks","entities","relations","error","stores"}。
    """
    if not _HAS_MEM and (not (_milvus.available or _milvus.connect()) or (extract_entities and not (_neo4j.available or _neo4j.connect()))):
        return {"chunks": 0, "entities": 0, "relations": 0, "error": "持久知识库不可用，请检查 Milvus / Neo4j；正文已保留，可稍后重建索引", "stores": _store_flags()}
    chunks = chunker.chunk_text(content, chapter_id, volume_id)
    if not chunks:
        return {"chunks": 0, "entities": 0, "relations": 0,
                "error": "切片为空", "stores": _store_flags()}
    texts = [c["text"] for c in chunks]
    try:
        cfg = await _resolve_embed_cfg()
        embeddings = await embedding.embed_texts(texts, cfg)
    except Exception as e:
        return {"chunks": 0, "entities": 0, "relations": 0,
                "error": f"Embedding 失败: {e}", "stores": _store_flags()}

    if not _HAS_MEM and not _milvus.available:
        return {"chunks": 0, "entities": 0, "relations": 0, "error": "Milvus 不可用", "stores": _store_flags()}
    rows = []
    for i, c in enumerate(chunks):
        rows.append({
            "id": int(chapter_id) * 10000 + int(c["chunk_idx"]),
            "chapter_id": int(chapter_id),
            "volume_id": int(volume_id or 0),
            "chunk_idx": int(c["chunk_idx"]),
            "text": c["text"],
            "embedding": embeddings[i],
        })

    if _milvus.available or _milvus.connect():
        _milvus.delete_chapter(user_id, book_id, chapter_id)
        n = _milvus.upsert(user_id, book_id, rows)
    else:
        _mem.delete_chapter(user_id, book_id, chapter_id)
        n = _mem.upsert(user_id, book_id, rows)

    if n != len(rows):
        return {"chunks": n, "entities": 0, "relations": 0, "error": "向量未完整写入，请重新入库", "stores": _store_flags()}
    ent_count = rel_count = 0
    if extract_entities:
        try:
            ents, rels = await _extract_entities_llm(content, model_choice)
            if _neo4j.available or _neo4j.connect():
                ent_count, rel_count = _neo4j.upsert_chapter(user_id, book_id, chapter_id, ents, rels)
            else:
                _mem.upsert_graph(user_id, book_id, chapter_id, ents, rels)
                ent_count, rel_count = len(ents), len(rels)
        except Exception as e:
            return {"chunks": n, "entities": 0, "relations": 0,
                    "error": f"实体抽取失败（切片已入库）: {e}", "stores": _store_flags()}
    return {"chunks": n, "entities": ent_count, "relations": rel_count,
            "error": None, "stores": _store_flags()}


async def _extract_segment(content: str, model_choice: dict | None) -> tuple[list[dict], list[dict]]:
    llm, _ = await get_llm(model_choice or {})
    from langchain_core.messages import HumanMessage, SystemMessage
    # 实体抽取是可选增强：加超时保险，避免网关异常导致整条 ingest 无限挂起
    for attempt in range(2):
        resp = await asyncio.wait_for(llm.bind(max_tokens=2048).ainvoke([
            SystemMessage(content=ENTITY_EXTRACT_SYSTEM),
            HumanMessage(content=f"请抽取以下章节的实体与关系：\n\n{content}" + ("\n上次输出不是合法JSON，请重新输出完整、精简的严格JSON对象。" if attempt else "")),
        ]),timeout=90)
        text=strip_code_fence(resp.content if isinstance(resp.content,str) else str(resp.content))
        try:
            data=json.loads(text)
            entities=data.get('entities',[]);relations=data.get('relations',[])
            if not isinstance(entities,list) or not isinstance(relations,list):raise ValueError('实体或关系格式错误')
            if any(not isinstance(e,dict) or not e.get('name') for e in entities):raise ValueError('实体缺少名称')
            return entities,relations
        except (ValueError,AttributeError) as exc:
            if attempt:raise ValueError('实体抽取未通过JSON校验，请稍后重新更新记忆') from exc



async def _extract_entities_llm(content,model_choice):
    # Process the whole plain-text chapter, not merely the first 4000 characters.
    import re
    text=re.sub(r'<[^>]+>','',content)
    entities={};relations={}
    for start in range(0,len(text),3200):
        ents,rels=await _extract_segment(text[start:start+3500],model_choice)
        for e in ents:
            key=(e.get('name'),e.get('type'))
            prior=entities.get(key)
            if prior and e.get('description')!=prior.get('description'):
                e={**e,'description':(prior.get('description','')+'；'+e.get('description',''))[:2000]}
            entities[key]=e
        for r in rels:
            if not isinstance(r,dict):raise ValueError('关系格式错误')
            relations[(r.get('from'),r.get('type'),r.get('to'))]=r
    return list(entities.values()),list(relations.values())

async def query_context(user_id: int, book_id: int, query: str, top_k: int = 5, allowed_chapter_ids: list[int] | None = None) -> dict:
    """混合检索：向量语义（Milvus）+ 图谱实体（Neo4j）。

    Returns {"chunks","entities","relations","query","error"}。
    """
    if not query or not query.strip():
        return {"chunks": [], "entities": [], "relations": [], "query": query}
    if allowed_chapter_ids == []:
        return {"chunks": [], "entities": [], "relations": [], "query": query}
    if not _HAS_MEM and (not (_milvus.available or _milvus.connect()) or not (_neo4j.available or _neo4j.connect())):
        return {'chunks':[],'entities':[],'relations':[],'query':query,'error':'持久故事记忆不可用，请检查 Milvus / Neo4j 后重试，系统不会静默忽略历史记忆'}
    try:
        cfg = await _resolve_embed_cfg()
        q_vec = await embedding.embed_query(query.strip(), cfg)
    except Exception as e:
        return {"chunks": [], "entities": [], "relations": [], "query": query,
                "error": f"Embedding 失败: {e}"}
    try:
        if _milvus.available or _milvus.connect():
            chunks = _milvus.search(user_id, book_id, q_vec, min(50,top_k*4) if allowed_chapter_ids is not None else top_k)
            if _neo4j.available or _neo4j.connect():
                graph = _neo4j.query_related(user_id, book_id, query.strip(), 8)
            else:
                graph = _mem.query_related(user_id, book_id, query.strip(), 8)
        else:
            chunks = _mem.search(user_id, book_id, q_vec, min(50,top_k*4) if allowed_chapter_ids is not None else top_k)
            graph = _mem.query_related(user_id, book_id, query.strip(), 8)
        if allowed_chapter_ids is not None:
            allowed=set(allowed_chapter_ids)
            chunks=[c for c in chunks if c.get('chapter_id') in allowed][:top_k]
            graph={key:[r for r in graph.get(key,[]) if r.get('chapter_id') in allowed] for key in ('entities','relations')}
        return {
            "chunks": chunks,
            "entities": graph.get("entities", []),
            "relations": graph.get("relations", []),
            "query": query,
        }

    except Exception:
        log.exception('Hybrid memory retrieval failed')
        return {'chunks':[],'entities':[],'relations':[],'query':query,'error':'故事记忆检索失败，请检查向量库和图数据库后重试'}


async def book_graph(user_id: int, book_id: int) -> dict:
    """整本书图谱（数据库页）。"""
    if _neo4j.available or _neo4j.connect():
        return _neo4j.book_graph(user_id, book_id)
    return _mem.book_graph(user_id, book_id)


async def related_to_name(user_id: int, book_id: int, name: str, limit: int = 20) -> dict:
    """配置实体页「从数据库加载」：按名称匹配实体与关系。"""
    if _neo4j.available or _neo4j.connect():
        return _neo4j.related_to_name(user_id, book_id, name, limit)
    return _mem.related_to_name(user_id, book_id, name, limit)


async def get_status(user_id: int, book_id: int, chapters: list[dict]) -> dict:
    """章节入库状态：chapters = [{chapter_id, number, title, has_content}]。"""
    result = []
    for ch in chapters:
        cid = ch["chapter_id"]
        if _milvus.available or _milvus.connect():
            chunk_count = _milvus.count_chunks(user_id, book_id, cid)
            ent_count = (_neo4j.entity_count(user_id, book_id, cid)
                         if (_neo4j.available or _neo4j.connect()) else 0)
        else:
            chunk_count = _mem.count_chunks(user_id, book_id, cid)
            ent_count = _mem.count_entities(user_id, book_id, cid)
        result.append({
            **ch,
            "chunk_count": chunk_count,
            "entity_count": ent_count,
            "ingested": bool(chunk_count) and ch.get("rag_status", "loaded")=="loaded",
        })
    total_chunks = sum(c["chunk_count"] for c in result)
    total_entities = sum(c["entity_count"] for c in result)
    return {"chapters": result, "total_chunks": total_chunks, "total_entities": total_entities}
