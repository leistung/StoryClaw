"""P1-8 阅读配置 API：阅读配置模板 CRUD + JSON 导入/导出."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.database import get_db
from app.models import ReadingConfig
from app.models import User
from app.schemas import ReadingConfigIn
from app.schemas import ReadingConfigOut
from app.schemas import ReadingConfigListOut

router = APIRouter(prefix="/reading-configs", tags=["reading-configs"])

@router.get("", response_model=ReadingConfigListOut)
async def list_configs(u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rs = await db.scalars(select(ReadingConfig).where(
        ReadingConfig.user_id == u.id
    ).order_by(ReadingConfig.is_default.desc(), ReadingConfig.id))
    items = [ReadingConfigOut.model_validate(r) for r in rs]
    return ReadingConfigListOut(items=items, total=len(items))

@router.post("", response_model=ReadingConfigOut)
async def create_config(data: ReadingConfigIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rc = ReadingConfig(user_id=u.id, book_id=data.book_id, name=data.name,
                       scene=data.scene, config_json=data.config_json, is_default=data.is_default)
    db.add(rc)
    await db.commit()
    await db.refresh(rc)
    return ReadingConfigOut.model_validate(rc)

@router.put("/{rcid}", response_model=ReadingConfigOut)
async def update_config(rcid: int, data: ReadingConfigIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rc = await db.get(ReadingConfig, rcid)
    if not rc or rc.user_id != u.id:
        raise HTTPException(404, "配置不存在")
    rc.name = data.name; rc.scene = data.scene
    rc.config_json = data.config_json; rc.is_default = data.is_default
    if data.book_id is not None:
        rc.book_id = data.book_id
    await db.commit()
    await db.refresh(rc)
    return ReadingConfigOut.model_validate(rc)

@router.delete("/{rcid}")
async def delete_config(rcid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rc = await db.get(ReadingConfig, rcid)
    if not rc or rc.user_id != u.id:
        raise HTTPException(404, "配置不存在")
    await db.delete(rc)
    await db.commit()
    return {"ok": True, "id": rcid}

@router.post("/import", response_model=ReadingConfigOut)
async def import_config(data: ReadingConfigIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """导入 JSON 配置为新模板（与 create 相同，语义入口）."""
    return await create_config(data, u, db)

@router.get("/{rcid}/export", response_model=dict)
async def export_config(rcid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rc = await db.get(ReadingConfig, rcid)
    if not rc or rc.user_id != u.id:
        raise HTTPException(404, "配置不存在")
    return {"name": rc.name, "scene": rc.scene, "config_json": rc.config_json}
