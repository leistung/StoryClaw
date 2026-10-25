"""Writer Tool Use 的实时工具执行器（backend 数据层）。

对应 storyclaw.nodes.tools.WRITER_TOOLS 的工具名，每个工具独立开 DB session
实时查询，返回可直接拼入 prompt 的文本。全部只读，无副作用。

工具列表：
- query_setting(entity_type, keyword)  查本书设定（角色/场景/物品/情节）
- query_memory(query)                  本书记忆检索（向量 + 图谱）
- get_outline(chapter_number)          指定章节大纲节点
- get_prev_chapter(chapter_number)     前一章内容摘要
"""
from __future__ import annotations

import json
import re

from sqlalchemy import select

from storyclaw.context import find_outline_node, summarize_prev

from ..database import AsyncSessionLocal
from ..models import Book, Chapter, ConfigEntity, Outline


async def execute_writer_tool(
    name: str, args: dict, user_id: int, book_id: int, chapter_id: int | None,
) -> str:
    async with AsyncSessionLocal() as db:
        book=await db.get(Book,book_id)
        current=await db.get(Chapter,chapter_id) if chapter_id else None
        if not book or book.user_id!=user_id or (chapter_id and (not current or current.book_id!=book_id)):
            return '无权读取此作品或章节'
        if current and name in ('get_prev_chapter','get_outline'):
            requested=int(args.get('chapter_number') or current.number)
            if requested>current.number:return '写作工具不能读取目标章之后的章节'
    handlers = {
        "query_setting": _tool_query_setting,
        "query_memory": _tool_query_memory,
        "get_outline": _tool_get_outline,
        "get_prev_chapter": _tool_get_prev_chapter,
        "get_book_meta": _tool_get_book_meta,
    }
    handler = handlers.get(name)
    if not handler:
        return f"未知工具: {name}"
    try:
        return await handler(args, user_id, book_id, chapter_id)
    except Exception as e:  # noqa: BLE001
        return f"工具 {name} 执行失败: {e}"


def _clean(text: str, limit: int) -> str:
    t = re.sub(r"<[^>]+>", "", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


async def _tool_query_setting(args, user_id: int, book_id: int, chapter_id) -> str:
    etype = (args.get("entity_type") or "").strip()
    keyword = (args.get("keyword") or "").strip()
    valid = {"character", "scene", "item", "plot", "world"}
    if etype not in valid:
        return f"entity_type 只能是 {sorted(valid)} 之一"
    async with AsyncSessionLocal() as db:
        rows = list(await db.scalars(select(ConfigEntity).where(
            ConfigEntity.book_id == book_id,
            ConfigEntity.entity_type == etype,
        ).order_by(ConfigEntity.sort_order, ConfigEntity.id)))
    matched = []
    for r in rows:
        if keyword and keyword not in r.name and keyword not in (r.description or ""):
            continue
        extra = ""
        if r.extra_json:
            try:
                extra = "，".join(f"{k}:{v}" for k, v in (r.extra_json.items() if isinstance(r.extra_json, dict) else []))[:150]
            except Exception:
                extra = ""
        matched.append(f"- {r.name}（{r.category}）：{_clean(r.description, 160)}{('，'+extra) if extra else ''}")
    if not matched:
        return f"未找到符合条件的{etype}设定" + (f"（关键词:{keyword}）" if keyword else "")
    return f"本书 {etype} 设定（{len(matched)} 条）：\n" + "\n".join(matched[:15])


async def _tool_query_memory(args, user_id: int, book_id: int, chapter_id) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "query 不能为空"
    from storyclaw.writing_context import query_memory_tool
    async with AsyncSessionLocal() as db:
        current=await db.get(Chapter,chapter_id) if chapter_id else None
        q=select(Chapter).where(Chapter.book_id==book_id,Chapter.rag_status=='loaded')
        if current:q=q.where(Chapter.number<current.number)
        rows=list(await db.scalars(q))
    return await query_memory_tool(user_id,book_id,query,[r.id for r in rows],{r.id:r.number for r in rows})


async def _tool_get_outline(args, user_id: int, book_id: int, chapter_id) -> str:
    num = int(args.get("chapter_number") or 0)
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(Outline).where(Outline.book_id == book_id))
        content = {}
        if row and row.content:
            try:
                content = json.loads(row.content)
            except Exception:
                content = {}
        if content.get('planning_mode')=='serial':
            chapter=await db.scalar(select(Chapter).where(Chapter.book_id==book_id,Chapter.number==num))
            if chapter:
                from .serial import blueprint_state
                state=await blueprint_state(db,chapter)
                if state['confirmed']:return json.dumps({'number':num,**state['plan']},ensure_ascii=False)
            return '本章章纲未确认或已过期，请先核对；不得自行从远期规划冒充本章章纲'
    node = find_outline_node(content, num)
    if not node:
        return f"大纲中未找到第{num}章节点"
    return json.dumps(node, ensure_ascii=False, indent=1)[:800]


async def _tool_get_prev_chapter(args, user_id: int, book_id: int, chapter_id) -> str:
    num = int(args.get("chapter_number") or 0)
    if num <= 1:
        return "（这是第一章，没有前一章）"
    async with AsyncSessionLocal() as db:
        prev = await db.scalar(select(Chapter).where(
            Chapter.book_id == book_id, Chapter.number == num - 1
        ))
    if not prev or not prev.content:
        return f"第{num-1}章不存在或为空"
    return f"第{num-1}章《{prev.title}》摘要：\n{summarize_prev(prev.content, 800)}"


async def _tool_get_book_meta(args, user_id: int, book_id: int, chapter_id) -> str:
    async with AsyncSessionLocal() as db:
        b = await db.get(Book, book_id)
        if not b:
            return "书籍不存在"
        return json.dumps({
            "title": b.title, "genre": b.genre, "intro": b.intro or "",
            "protagonist_name": b.protagonist_name or "",
            "protagonist_intro": b.protagonist_intro or "",
            "target_chapters": b.target_chapters,
            "per_chapter_words": b.per_chapter_words,
        }, ensure_ascii=False)
