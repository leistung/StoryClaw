"""P2-10 充值 API."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.deps import get_current_user
from ..database import get_db
from ..models import User, CreditsLedger
from ..services.configs import load_membership

router = APIRouter(prefix="/recharge", tags=["recharge"])


class PurchaseIn(BaseModel):
    membership_id: str


@router.get("/memberships")
async def list_memberships():
    cfg = load_membership()
    from ..config import settings
    return {**cfg, "payments_enabled": False, "activation_mode": "manual_review"}


@router.post("/purchase")
async def purchase(
    data: PurchaseIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(503, "当前仅支持运营人工开通，请通过会员页提交申请；未接入在线支付")


@router.get("/history")
async def recharge_history(
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rs = await db.scalars(select(CreditsLedger).where(
        CreditsLedger.user_id == u.id, CreditsLedger.reason.like("充值%")
    ).order_by(CreditsLedger.created_at.desc()))
    return [{"id": r.id, "delta": r.delta, "reason": r.reason,
             "created_at": str(r.created_at) if r.created_at else None} for r in rs]
