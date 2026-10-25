"""断点恢复 CheckPointer：PostgresSaver（生产）/ InMemorySaver（降级）。"""
from __future__ import annotations

import logging
from typing import Optional

from langgraph.checkpoint.memory import InMemorySaver

log = logging.getLogger("storyclaw.runtime.execution.checkpointer")


async def build_checkpointer(dsn: Optional[str] = None):
    """优先 AsyncPostgresSaver；失败降级 InMemorySaver。

    dsn 示例：postgresql+asyncpg://user:pass@host:5432/db
    AsyncPostgresSaver 使用 psycopg 驱动，会自动去掉 +asyncpg 前缀。

    注意：不要用 `AsyncPostgresSaver.from_conn_string(...)` 的 async 上下文管理器——
    它在生成器 GC 时会关闭连接（"the connection is closed"）。这里自己创建并持有
    psycopg AsyncConnection（连接随应用进程常驻），直接把 conn 传给构造器。
    """
    if dsn:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            clean = dsn.replace("+asyncpg", "").replace("+psycopg2", "")
            conn = await psycopg.AsyncConnection.connect(
                clean, autocommit=True, prepare_threshold=0, row_factory=dict_row,
            )
            saver = AsyncPostgresSaver(conn=conn)
            await saver.setup()
            log.info("PostgresSaver 断点恢复已启用")
            return saver
        except Exception as e:
            log.warning("PostgresSaver 不可用，降级 InMemorySaver: %s", e)
    return InMemorySaver()
