"""P1-7 配置实体 API：角色/场景/物品/情节/大纲 统一 CRUD + RAG 关联加载.

路由前缀：/api/books/{bid}/config/{entity_type}
entity_type: character | scene | item | plot | outline
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..core.deps import get_current_user
from ..database import get_db
from ..models import Book, ConfigEntity, EntityKv, User
from ..schemas import (
    ConfigEntityCreateIn, ConfigEntityListOut, ConfigEntityOut,
    ConfigEntityUpdateIn, EntityKvOut, RagRelatedOut,
)

router = APIRouter(prefix="/books/{bid}/config", tags=["config-entities"])

VALID_TYPES = {"character", "scene", "item", "plot", "outline", "world"}


async def _check_book(bid: int, u: User, db: AsyncSession) -> Book:
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")
    return b


async def _entity_to_out(db: AsyncSession, e: ConfigEntity, entity_type: str) -> ConfigEntityOut:
    kvs = await db.scalars(select(EntityKv).where(
        EntityKv.entity_type == entity_type, EntityKv.entity_id == e.id))
    return ConfigEntityOut(
        id=e.id, book_id=e.book_id, entity_type=e.entity_type,
        category=e.category, name=e.name, description=e.description,
        image_url=e.image_url, extra_json=e.extra_json, sort_order=e.sort_order,
        kv=[EntityKvOut.model_validate(k) for k in kvs],
    )


@router.get("/{entity_type}", response_model=ConfigEntityListOut)
async def list_entities(
    bid: int, entity_type: str,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出某类配置实体（含 kv）."""
    if entity_type not in VALID_TYPES:
        raise HTTPException(400, f"未知类型: {entity_type}，可选: {VALID_TYPES}")
    await _check_book(bid, u, db)
    rs = await db.scalars(select(ConfigEntity).where(
        ConfigEntity.book_id == bid, ConfigEntity.entity_type == entity_type
    ).order_by(ConfigEntity.sort_order, ConfigEntity.id))
    items = [await _entity_to_out(db, e, entity_type) for e in rs]
    return ConfigEntityListOut(book_id=bid, entity_type=entity_type, items=items, total=len(items))


@router.post("/{entity_type}", response_model=ConfigEntityOut)
async def create_entity(
    bid: int, entity_type: str, data: ConfigEntityCreateIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建配置实体."""
    if entity_type not in VALID_TYPES:
        raise HTTPException(400, f"未知类型: {entity_type}")
    book=await _check_book(bid,u,db)
    await db.refresh(book,with_for_update=True)
    from ..services.serial import assert_book_idle,invalidate_book
    await assert_book_idle(db,bid)
    e = ConfigEntity(
        book_id=bid, entity_type=entity_type, category=data.category,
        name=data.name, description=data.description,
        image_url=data.image_url, extra_json=data.extra_json,
    )
    db.add(e)
    await db.flush()
    for kv in data.kv:
        db.add(EntityKv(entity_type=entity_type, entity_id=e.id, key=kv.key, value=kv.value))
    await invalidate_book(db,bid,'作者设定已变更，请复核既有正文与后续章纲')
    await db.commit()
    await db.refresh(e)
    return await _entity_to_out(db, e, entity_type)


@router.put("/{entity_type}/{eid}", response_model=ConfigEntityOut)
async def update_entity(
    bid: int, entity_type: str, eid: int, data: ConfigEntityUpdateIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新配置实体（含 kv 替换）."""
    if entity_type not in VALID_TYPES:
        raise HTTPException(400, f"未知类型: {entity_type}")
    book=await _check_book(bid,u,db)
    await db.refresh(book,with_for_update=True)
    from ..services.serial import assert_book_idle,invalidate_book
    await assert_book_idle(db,bid)
    e = await db.get(ConfigEntity, eid)
    if not e or e.book_id != bid or e.entity_type != entity_type:
        raise HTTPException(404, "实体不存在")
    if data.name is not None:
        e.name = data.name
    if data.category is not None:
        e.category = data.category
    if data.description is not None:
        e.description = data.description
    if data.image_url is not None:
        e.image_url = data.image_url
    if data.extra_json is not None:
        e.extra_json = data.extra_json
    if data.sort_order is not None:
        e.sort_order = data.sort_order
    if data.kv is not None:
        await db.execute(delete(EntityKv).where(
            EntityKv.entity_type == entity_type, EntityKv.entity_id == eid))
        for kv in data.kv:
            db.add(EntityKv(entity_type=entity_type, entity_id=eid, key=kv.key, value=kv.value))
    await invalidate_book(db,bid,'作者设定已变更，请复核既有正文与后续章纲')
    await db.commit()
    await db.refresh(e)
    return await _entity_to_out(db, e, entity_type)


@router.delete("/{entity_type}/{eid}")
async def delete_entity(
    bid: int, entity_type: str, eid: int,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除配置实体（含 kv 级联删除）."""
    if entity_type not in VALID_TYPES:
        raise HTTPException(400, f"未知类型: {entity_type}")
    book=await _check_book(bid,u,db)
    await db.refresh(book,with_for_update=True)
    from ..services.serial import assert_book_idle,invalidate_book
    await assert_book_idle(db,bid)
    e = await db.get(ConfigEntity, eid)
    if not e or e.book_id != bid or e.entity_type != entity_type:
        raise HTTPException(404, "实体不存在")
    await db.execute(delete(EntityKv).where(
        EntityKv.entity_type == entity_type, EntityKv.entity_id == eid))
    await db.delete(e)
    await invalidate_book(db,bid,'作者设定已变更，请复核既有正文与后续章纲')
    await db.commit()
    return {"ok": True, "id": eid}


@router.get("/{entity_type}/{eid}/rag-related", response_model=RagRelatedOut)
async def load_rag_related(
    bid: int, entity_type: str, eid: int,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从数据库加载：与该实体相关的图谱实体关系 + 相似片段.

    存储层在 packages/storyclaw/rag（Neo4j 实体关系 + Milvus 语义片段）。
    实体：按名称模糊匹配 Neo4j StoryEntity
    关系：图谱中与实体相连的一跳关系
    片段：用实体名做向量检索，取语义相似切片
    """
    from ..models import Chapter
    from ..schemas import RagChunkOut, RagEntityOut, RagRelationOut
    from storyclaw.rag import service as rag_svc

    if entity_type not in VALID_TYPES:
        raise HTTPException(400, f"未知类型: {entity_type}")
    await _check_book(bid, u, db)
    e = await db.get(ConfigEntity, eid)
    if not e or e.book_id != bid or e.entity_type != entity_type:
        raise HTTPException(404, "实体不存在")

    name = e.name.strip()
    related = (await rag_svc.related_to_name(u.id, bid, name, 20)) if name else {"entities": [], "relations": []}

    # 语义相似片段：用实体名向量检索
    chunk_res = (await rag_svc.query_context(u.id, bid, name, 5)) if name else {"chunks": []}
    cids = list({c["chapter_id"] for c in (chunk_res.get("chunks") or [])})
    ch_map: dict[int, Chapter] = {}
    if cids:
        rows = await db.execute(select(Chapter).where(Chapter.id.in_(cids)))
        ch_map = {c.id: c for c in rows.scalars()}

    rag_chunks = [
        RagChunkOut(
            text=c.get("text", ""), chapter_id=c["chapter_id"],
            volume_id=c.get("volume_id"), chunk_idx=c.get("chunk_idx"),
            score=c.get("score", 0.0),
            chapter_title=(ch_map.get(c["chapter_id"]).title if ch_map.get(c["chapter_id"]) else "") or "",
            chapter_number=(ch_map.get(c["chapter_id"]).number if ch_map.get(c["chapter_id"]) else 0),
        )
        for c in (chunk_res.get("chunks") or [])
    ]

    return RagRelatedOut(
        entities=[
            RagEntityOut(
                id=abs(hash(en.get("name", ""))) % (2 ** 31),
                name=en.get("name", ""), type=en.get("type", "character"),
                description=(en.get("description") or "") or "", chapter_id=en.get("chapter_id"),
            )
            for en in (related.get("entities") or [])
        ],
        relations=[
            RagRelationOut.model_validate({
                "from": r.get("from"), "to": r.get("to"),
                "type": r.get("type", "RELATES_TO"), "chapter_id": r.get("chapter_id"),
            })
            for r in (related.get("relations") or [])
        ],
        chunks=rag_chunks,
    )
