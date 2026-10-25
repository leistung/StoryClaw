"""Memory Manager（backend 数据层）。

短期记忆：会话 messages（PG messages 表，按 thread_id 索引）
长期记忆：用户写作偏好（user_memories 表）

纯偏好逻辑 / 编解码在 backend/packages/harness/storyclaw/context/memory.py，
本模块只负责 DB 读写，agent 侧复用同一份默认偏好与编码规则。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storyclaw.context.memory import decode
from storyclaw.context.memory import default_memory
from storyclaw.context.memory import encode
from storyclaw.context.memory import merge_memory

from app.models import UserMemory


async def load_user_memory(user_id: int, db: AsyncSession) -> dict[str, Any]:
    """读取用户长期偏好，合并默认值。返回 dict（可直接放入 AgentState.user_memory）。"""
    prefs = default_memory()
    rs = await db.scalars(select(UserMemory).where(UserMemory.user_id == user_id))
    rows: dict[str, Any] = {}
    for m in rs:
        rows[m.key] = decode(m.value)
    return merge_memory(rows)


async def save_user_memory(user_id: int, key: str, value: Any, db: AsyncSession) -> None:
    """upsert 单条偏好。"""
    v = encode(value)
    existing = await db.scalar(select(UserMemory).where(
        UserMemory.user_id == user_id, UserMemory.key == key
    ))
    if existing:
        existing.value = v
    else:
        db.add(UserMemory(user_id=user_id, key=key, value=v))
    await db.commit()
