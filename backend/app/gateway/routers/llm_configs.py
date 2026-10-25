from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin import get_admin_user as get_current_user
from app.core.security import encrypt_api_key
from app.database import get_db
from app.models import User
from app.models import UserLLMConfig
from app.schemas import LLMConfigIn
from app.schemas import LLMConfigOut
from app.schemas import LLMConfigUpdate

router = APIRouter(prefix="/llm-configs", tags=["llm-configs"])


def _to_out(c: UserLLMConfig) -> LLMConfigOut:
    return LLMConfigOut(
        id=c.id, name=c.name, format=c.format, base_url=c.base_url, model=c.model,
        temperature=c.temperature, max_tokens=c.max_tokens, is_default=c.is_default,
        has_key=bool(c.api_key_enc),
        embedding_model=c.embedding_model,
        embedding_base_url=c.embedding_base_url,
        has_embedding_key=bool(c.embedding_api_key_enc),
    )


@router.get("", response_model=list[LLMConfigOut])
async def list_cfg(u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rs = await db.scalars(select(UserLLMConfig).where(UserLLMConfig.user_id == u.id).order_by(UserLLMConfig.id))
    return [_to_out(c) for c in rs]


@router.post("", response_model=LLMConfigOut)
async def create_cfg(data: LLMConfigIn, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not u.is_admin:
        raise HTTPException(403, "仅本地版本可配置 LLM")
    if data.is_default:
        await db.execute(update(UserLLMConfig).where(UserLLMConfig.user_id == u.id).values(is_default=False))
    c = UserLLMConfig(
        user_id=u.id, name=data.name, format=data.format, base_url=data.base_url, model=data.model,
        api_key_enc=encrypt_api_key(data.api_key), temperature=data.temperature,
        max_tokens=data.max_tokens, is_default=data.is_default,
        embedding_model=data.embedding_model,
        embedding_base_url=data.embedding_base_url,
        embedding_api_key_enc=encrypt_api_key(data.embedding_api_key),
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _to_out(c)


@router.put("/{cid}", response_model=LLMConfigOut)
async def update_cfg(cid: int, data: LLMConfigUpdate, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(UserLLMConfig, cid)
    if not c or c.user_id != u.id:
        raise HTTPException(404, "配置不存在")
    if data.is_default:
        await db.execute(update(UserLLMConfig).where(UserLLMConfig.user_id == u.id).values(is_default=False))
    for k, v in data.model_dump(exclude_unset=True).items():
        if k == "api_key":
            c.api_key_enc = encrypt_api_key(v)
        elif k == "embedding_api_key":
            c.embedding_api_key_enc = encrypt_api_key(v)
        else:
            setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return _to_out(c)


@router.delete("/{cid}")
async def delete_cfg(cid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(UserLLMConfig, cid)
    if not c or c.user_id != u.id:
        raise HTTPException(404, "配置不存在")
    await db.delete(c)
    await db.commit()
    return {"ok": True}
