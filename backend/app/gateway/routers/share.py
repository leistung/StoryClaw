import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Message
from app.models import User
from app.schemas import ShareOut
from app.schemas import ShareView

router = APIRouter(prefix="", tags=["share"])


@router.post("/messages/{mid}/share", response_model=ShareOut)
async def create_share(mid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    m = await db.get(Message, mid)
    if not m or m.user_id != u.id or m.role != "assistant":
        raise HTTPException(404, "消息不存在")
    if not m.share_token:
        m.share_token = uuid.uuid4().hex[:16]
        await db.commit()
    return ShareOut(share_token=m.share_token)


@router.get("/share/{token}", response_model=ShareView)
async def view_share(token: str, db: AsyncSession = Depends(get_db)):
    m = await db.scalar(select(Message).where(Message.share_token == token, Message.role == "assistant"))
    if not m:
        raise HTTPException(404, "分享不存在或已失效")
    author = await db.get(User, m.user_id)
    return ShareView(
        content=m.content, model=m.model, in_tokens=m.in_tokens, out_tokens=m.out_tokens,
        credits_cost=m.credits_cost, created_at=m.created_at.isoformat() if m.created_at else None,
        username=author.username if author else None,
    )
