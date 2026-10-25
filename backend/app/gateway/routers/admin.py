"""P2-10 后台管理 API."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.admin import get_admin_user
from app.database import get_db
from app.models import User
from app.models import CreditsLedger

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    page: int = 1, limit: int = 50,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if page < 1 or not 1 <= limit <= 100:
        raise HTTPException(400, "分页参数无效")
    rs = await db.scalars(select(User).order_by(User.id).offset((page - 1) * limit).limit(limit))
    return [{"id": u.id, "username": u.username, "version": u.version,
             "credits_balance": u.credits_balance, "is_admin": u.is_admin,
             "created_at": str(u.created_at) if u.created_at else None} for u in rs]


@router.get("/credits-report")
async def credits_report(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # 按用户聚合
    by_user = await db.execute(
        select(CreditsLedger.user_id,
               func.sum(CreditsLedger.delta).label("total_delta"),
               func.count().label("tx_count"))
        .group_by(CreditsLedger.user_id).order_by(func.sum(CreditsLedger.delta)))
    # 按模型聚合
    by_model = await db.execute(
        select(CreditsLedger.model,
               func.sum(CreditsLedger.delta).label("total_delta"),
               func.count().label("tx_count"))
        .group_by(CreditsLedger.model))
    return {
        "by_user": [{"user_id": r[0], "total_delta": r[1], "tx_count": r[2]} for r in by_user],
        "by_model": [{"model": r[0] or "N/A", "total_delta": r[1], "tx_count": r[2]} for r in by_model],
    }


# 配置编辑不再写只读 YAML 挂载，统一存 PostgreSQL。
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from app.models import Book
from app.models.platform import PlatformEvent
from app.services.platform.configs import _load
from app.services.platform.platform import save_config
from app.core.security import encrypt_api_key

class CreditAdjustment(BaseModel):
    delta: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=3, max_length=64)
    request_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")

class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    model: str = Field(default="", max_length=128)
    format: Literal["openai_chat", "openai_responses", "anthropic"] = "openai_chat"
    base_url: str = ""
    enabled: bool = True
    business_only: bool = True
    thinking: Literal["enabled", "disabled"] | None = None
    context_limit: int = Field(default=32000, ge=1024, le=2000000)
    api_key: str | None = Field(default=None, max_length=512)
    has_key: bool = False
    fallback_models: list[str] = Field(default_factory=list, max_length=1)

class ModelCatalog(BaseModel):
    models: list[ModelEntry] = Field(max_length=100)
    defaults: dict = Field(default_factory=dict)

class EmbeddingConfig(BaseModel):
    dimensions: int = Field(default=1024, ge=1, le=32768)
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=128)
    base_url: str
    api_key: str | None = Field(default=None, max_length=512)
    has_key: bool = False

@router.get("/overview")
async def overview(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    from app.models import Chapter
    return {
        "users": await db.scalar(select(func.count()).select_from(User)),
        "books": await db.scalar(select(func.count()).select_from(Book)),
        "chapters": await db.scalar(select(func.count()).select_from(Chapter)),
        "credits": await db.scalar(select(func.coalesce(func.sum(User.credits_balance), 0))),
    }

@router.get("/users/{uid}")
async def user_details(uid: int, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, uid)
    if not user:
        raise HTTPException(404, "用户不存在")
    books = await db.scalars(select(Book).where(Book.user_id == uid).order_by(Book.id.desc()).limit(100))
    ledger = await db.scalars(select(CreditsLedger).where(CreditsLedger.user_id == uid).order_by(CreditsLedger.id.desc()).limit(100))
    db.add(PlatformEvent(kind="audit", actor_id=admin.id, action="user.inspect", target=str(uid), details={}))
    await db.commit()
    return {"id": user.id, "username": user.username, "credits_balance": user.credits_balance,
            "books": [{"id": b.id, "title": b.title, "genre": b.genre} for b in books],
            "ledger": [{"id": x.id, "delta": x.delta, "reason": x.reason, "model": x.model, "created_at": str(x.created_at)} for x in ledger]}

@router.post("/users/{uid}/credits")
async def adjust_credits(uid: int, data: CreditAdjustment, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    if not data.delta:
        raise HTTPException(400, "积分变化不能为零")
    user = await db.scalar(select(User).where(User.id == uid).with_for_update())
    if not user:
        raise HTTPException(404, "用户不存在")
    target = f"credits:{uid}:{data.request_id}"
    prior = await db.scalar(select(PlatformEvent).where(PlatformEvent.kind == "audit", PlatformEvent.target == target))
    if prior:
        if prior.details != {"delta": data.delta, "reason": data.reason}:
            raise HTTPException(409, "同一请求编号不能用于不同的积分调整")
        return {"ok": True, "credits_balance": user.credits_balance}
    if user.credits_balance + data.delta < 0:
        raise HTTPException(400, "扣减后余额不能为负")
    user.credits_balance += data.delta
    db.add(CreditsLedger(user_id=uid, delta=data.delta, reason=data.reason, model="admin"))
    db.add(PlatformEvent(kind="audit", actor_id=admin.id, action="credits.adjust", target=target,
                         details={"delta": data.delta, "reason": data.reason}))
    await db.commit()
    return {"ok": True, "credits_balance": user.credits_balance}

@router.get("/logs")
async def logs(kind: Literal["request", "audit"] = "audit", page: int = 1, limit: int = 50,
               admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    if page < 1 or not 1 <= limit <= 100:
        raise HTTPException(400, "分页参数无效")
    rows = await db.scalars(select(PlatformEvent).where(PlatformEvent.kind == kind)
        .order_by(PlatformEvent.id.desc()).offset((page-1)*limit).limit(limit))
    return [{"id": x.id, "actor_id": x.actor_id, "action": x.action, "target": x.target,
             "details": x.details, "created_at": str(x.created_at)} for x in rows]

@router.get("/models")
async def models(admin: User = Depends(get_admin_user)):
    data = _load("models.yaml")
    for m in data.get("models", []):
        m["has_key"] = bool(m.pop("api_key_enc", None))
        m.pop("api_key", None)
    return data

@router.put("/models")
async def update_models(data: ModelCatalog, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    ids = [m.id for m in data.models]
    if len(ids) != len(set(ids)) or "custom-local" in ids:
        raise HTTPException(400, "模型编号必须唯一且不能使用旧版本编号")
    if not any(m.enabled for m in data.models):
        raise HTTPException(400, "至少启用一个平台模型")
    by_id = {m.id: m for m in data.models}
    for m in data.models:
        for fallback in m.fallback_models:
            target = by_id.get(fallback)
            if not target or fallback == m.id or not target.enabled or target.fallback_models:
                raise HTTPException(400, "降级模型必须已启用、不同于主模型，且不能嵌套降级")
    old = {m["id"]: m for m in _load("models.yaml").get("models", [])}
    value = data.model_dump()
    for m in value["models"]:
        key = m.pop("api_key", None)
        m.pop("has_key", None)
        m["api_key_enc"] = encrypt_api_key(key) if key else old.get(m["id"], {}).get("api_key_enc")
        if m["base_url"] and not m["base_url"].startswith(("https://", "http://")):
            raise HTTPException(400, "模型地址必须使用 http 或 https")
    await save_config(db, "models.yaml", value, admin.id)
    return {"ok": True}

@router.get("/embedding")
async def embedding(admin: User = Depends(get_admin_user)):
    value = _load("embedding.yaml")
    value["has_key"] = bool(value.pop("api_key_enc", None))
    return value

@router.put("/embedding")
async def update_embedding(data: EmbeddingConfig, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    if not data.base_url.startswith(("https://", "http://")):
        raise HTTPException(400, "Embedding 地址必须使用 http 或 https")
    from storyclaw.config.settings import settings as agent_settings
    if data.dimensions != agent_settings.milvus_dim:
        raise HTTPException(400, f"向量维度必须与 Milvus 一致：{agent_settings.milvus_dim}")
    old = _load("embedding.yaml")
    # 已建立知识库后切换向量模型须显式重建索引，避免同维度模型混用。
    if old.get("model") and any(old.get(k) != getattr(data, k) for k in ("model", "base_url", "dimensions")):
        raise HTTPException(409, "切换向量模型需迁移索引；当前仅支持首次配置和更新密钥")
    value = data.model_dump(exclude={"has_key", "api_key"})
    value["api_key_enc"] = encrypt_api_key(data.api_key) if data.api_key else old.get("api_key_enc")
    await save_config(db, "embedding.yaml", value, admin.id)
    return {"ok": True}

@router.get('/model-calls')
async def model_calls(page:int=1,admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    from app.models.studio import ModelCall
    if page<1:raise HTTPException(422,'页码无效')
    rows=await db.scalars(select(ModelCall).order_by(ModelCall.created_at.desc()).offset((page-1)*50).limit(50))
    return [{'id':r.id,'actor_id':r.user_id,'action':r.status,'target':r.model,'created_at':r.created_at,
        'details':{'reserved':r.reserved,'credits_cost':r.cost,'usage':r.usage,'job_id':r.job_id,'plan_id':r.plan_id}} for r in rows]

from pydantic import BaseModel,Field,ConfigDict
class UsageReceiptIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:str=Field(min_length=16,max_length=100)
    input_tokens:int=Field(ge=0,le=100000000)
    output_tokens:int=Field(ge=0,le=100000000)
    supplier_reference:str=Field(min_length=3,max_length=255)
    note:str=Field(min_length=5,max_length=4000)
    adjust_user_balance:bool=False
@router.post('/model-calls/{cid}/reconcile')
async def reconcile_usage(cid:str,data:UsageReceiptIn,admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    from app.services.platform.usage_reconciliation import reconcile
    return await reconcile(db,admin,cid,data)
@router.get('/cleanup-tasks')
async def cleanup_tasks(admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    from app.models.operations import CleanupTask
    rows=await db.scalars(select(CleanupTask).order_by(CleanupTask.created_at.desc()).limit(100))
    return [{k:getattr(r,k) for k in ('id','kind','status','attempts','error','due_at')} for r in rows]
@router.post('/cleanup-tasks/{tid}/retry')
async def retry_cleanup(tid:str,admin:User=Depends(get_admin_user),db:AsyncSession=Depends(get_db)):
    from app.models.operations import CleanupTask
    from datetime import datetime,timezone
    row=await db.scalar(select(CleanupTask).where(CleanupTask.id==tid).with_for_update())
    if not row:raise HTTPException(404,'清理记录不存在')
    if row.status!='failed':raise HTTPException(409,'仅失败的清理任务需要重试')
    row.status='queued';row.attempts=0;row.due_at=datetime.now(timezone.utc);await db.commit();return {'status':'queued'}

@router.get("/{kind}")
async def get_config(kind: Literal["pricing", "membership"], admin: User = Depends(get_admin_user)):
    return _load(f"{kind}.yaml")

@router.put("/{kind}")
async def update_config(kind: Literal["pricing", "membership"], data: dict,
                        admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    from math import isfinite
    if kind == "pricing":
        pricing = data.get("pricing")
        if not isinstance(pricing, dict):
            raise HTTPException(400, "pricing 必须为对象")
        for prices in pricing.values():
            if not isinstance(prices, dict) or any(type(prices.get(k)) not in (int, float) or not isfinite(prices[k]) or prices[k] < 0 for k in ("input_price", "output_price")):
                raise HTTPException(400, "模型输入和输出价格必须为非负数")
        defaults = data.get("defaults", {})
        if not isinstance(defaults, dict) or type(defaults.get("free_quota", 0)) is not int or not 0 <= defaults.get("free_quota", 0) <= 1000000:
            raise HTTPException(400, "注册赠送积分必须为 0 到 1000000 的整数")
        rate=defaults.get("embedding_credits_per_1k",1)
        if type(rate) not in (int,float) or not isfinite(rate) or rate<0:raise HTTPException(400,"向量模型积分价格必须为有效非负数")
        if defaults.get("price_base", "per_1k_tokens") not in {"per_token", "per_1k_tokens", "per_1m_tokens"}:
            raise HTTPException(400, "计价单位无效")
    else:
        rows = data.get("memberships")
        if not isinstance(rows, list) or any(not isinstance(x, dict) or not x.get("id") or not isinstance(x.get("name"), str) or type(x.get("bonus_credits", 0)) is not int or x.get("bonus_credits", 0) < 0 for x in rows):
            raise HTTPException(400, "会员套餐格式无效")
        ids = [x["id"] for x in rows]
        if len(ids) != len(set(ids)) or any(type(x.get("price_cny")) not in (int, float) or not isfinite(x["price_cny"]) or x["price_cny"] < 0 or type(x.get("duration_days")) is not int or x["duration_days"] < 1 for x in rows):
            raise HTTPException(400, "套餐编号必须唯一，价格需非负且有效期为正整数")
    await save_config(db, f"{kind}.yaml", data, admin.id)
    return {"ok": True}
