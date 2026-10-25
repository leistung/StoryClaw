"""RAG API（薄网关）：章节入库 + 检索 + 状态查询。

存储与检索逻辑（Milvus 向量 + Neo4j 图谱 + 内存降级）统一在
backend/packages/harness/storyclaw/rag/service.py；本模块只负责鉴权 + 结果富化（章节标题/序号）。
- POST /chapters/{cid}/ingest  章节切片->向量入库(Milvus) + LLM 抽实体->图谱(Neo4j)
- POST /rag/query              混合检索（向量语义 + 图谱实体关系）
- GET  /books/{bid}/rag-status 书籍 RAG 入库状态
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storyclaw.rag import service as rag_svc

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import User
from app.services.writing.revisions import chapter_hash
from app.services.writing.revisions import assert_editable
from app.schemas import IngestOut
from app.schemas import RagQueryIn
from app.schemas import RagQueryOut
from app.schemas import RagStatusOut

class IngestReview(BaseModel):
    reviewed_hash:str=Field(min_length=64,max_length=64)



def _stable_id(name: str) -> int:
    """为图谱实体生成稳定的前端 key（Neo4j 无自增 id）。"""
    return abs(hash(name)) % (2 ** 31)


# ============ 章节入库 ============

async def ingest_chapter_endpoint(
    cid: int,
    data: IngestReview,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """章节入库：切片 -> Milvus 向量入库 + LLM 实体抽取 -> Neo4j 图谱。"""
    c = await db.get(Chapter, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    b = await db.get(Book, c.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "章节不存在")
    if not c.content:
        raise HTTPException(400, "章节无内容，请先生成或编辑")

    await assert_editable(db,cid)
    before_hash=chapter_hash(c)
    if data.reviewed_hash!=before_hash:raise HTTPException(409,'正文已变更，请审阅当前版本后重新确认')
    c.rag_status='pending'
    await db.commit()
    model_choice = {"kind": "business"}

    from app.services.knowledge.index_manifest import stage
    from app.services.knowledge.index_manifest import activate
    manifest=await stage(db,c,before_hash)
    result = await rag_svc.ingest_text(
        user_id=u.id, book_id=c.book_id, chapter_id=manifest.physical_id,
        volume_id=c.volume_id, content=c.content,
        model_choice=model_choice, extract_entities=True,
    )

    await db.refresh(c)
    if chapter_hash(c)!=before_hash:
        result["error"]="正文在入库期间发生修改，请重新更新故事记忆"
    # 更新章节 rag_status
    rag_status = "loaded" if result["chunks"] > 0 and not result.get("error") and result.get("stores", {}).get("vector") == "milvus" and result.get("stores", {}).get("graph") == "neo4j" else "pending"
    okay=await activate(db,manifest,c,result,before_hash)
    rag_status="loaded" if okay else "pending"
    c.rag_status = rag_status
    if rag_status=='loaded':
        from app.services.writing.serial import acknowledge_index
        await acknowledge_index(db,c)
    await db.commit()

    return IngestOut(
        chapter_id=cid,
        chunks=result["chunks"],
        entities=result["entities"],
        relations=result["relations"],
        rag_status=rag_status,
        error=result.get("error"),
    )


# ============ 检索查询 ============

async def rag_query(
    data: RagQueryIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """混合检索：Milvus 向量语义 topK + Neo4j 相关实体关系。"""
    b = await db.get(Book, data.book_id)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    if not data.query.strip():
        raise HTTPException(400, "查询内容不能为空")

    allowed=list(await db.scalars(select(Chapter.id).where(Chapter.book_id==data.book_id,Chapter.rag_status=="loaded")))
    result = await rag_svc.query_context(
        user_id=u.id, book_id=data.book_id,
        query=data.query, top_k=data.top_k, allowed_chapter_ids=allowed,
    )

    # 富化：章节标题/序号 + 实体稳定 id
    chunks: list = []
    raw_chunks = result.get("chunks") or []
    if raw_chunks:
        cids = list({c["chapter_id"] for c in raw_chunks})
        rows = await db.execute(select(Chapter).where(Chapter.id.in_(cids)))
        ch_map = {c.id: c for c in rows.scalars()}
        for c in raw_chunks:
            ch = ch_map.get(c["chapter_id"])
            chunks.append({
                **c,
                "chapter_title": ch.title if ch else "",
                "chapter_number": ch.number if ch else 0,
            })
    entities = [
        {**e, "id": _stable_id(e.get("name", ""))}
        for e in (result.get("entities") or [])
    ]
    return RagQueryOut(
        chunks=chunks,
        entities=entities,
        relations=result.get("relations", []),
        query=result.get("query", data.query),
        error=result.get("error"),
    )


# ============ 书籍 RAG 状态 ============

async def rag_status(
    bid: int,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询书籍所有章节的 RAG 入库状态（Milvus 切片数 + Neo4j 实体数）。"""
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")

    chapters = await db.scalars(select(Chapter).where(
        Chapter.book_id == bid).order_by(Chapter.number))
    ch_list = [
        {"chapter_id": c.id, "number": c.number, "title": c.title, "has_content": bool(c.content), "rag_status":c.rag_status}
        for c in chapters
    ]
    status = await rag_svc.get_status(u.id, bid, ch_list)
    return RagStatusOut(
        book_id=bid,
        chapters=status.get("chapters", []),
        total_chunks=status.get("total_chunks", 0),
        total_entities=status.get("total_entities", 0),
    )

from app.services.platform.metering import metered
ingest_chapter_endpoint = metered(ingest_chapter_endpoint)

rag_query = metered(rag_query)
