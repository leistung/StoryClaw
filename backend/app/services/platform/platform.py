"""平台配置持久化；YAML 仅作为未配置时的初始值。"""
from copy import deepcopy
from sqlalchemy import select
from app.models import PlatformConfig
from app.models import PlatformEvent
from app.services.platform.configs import _snapshot

async def refresh_configs(db):
    rows = await db.scalars(select(PlatformConfig))
    _snapshot.clear()
    _snapshot.update({row.key: deepcopy(row.value) for row in rows})

async def save_config(db, key, value, actor_id):
    # 同一配置并发保存采用 PostgreSQL upsert，避免首写主键冲突。
    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy import func
    await db.execute(insert(PlatformConfig).values(key=key, value=value).on_conflict_do_update(
        index_elements=[PlatformConfig.key], set_={"value": value, "updated_at": func.now()}))
    db.add(PlatformEvent(kind="audit", actor_id=actor_id, action="config.update", target=key, details={}))
    await db.commit()
    await refresh_configs(db)
