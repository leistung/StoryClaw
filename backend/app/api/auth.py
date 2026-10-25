from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import get_current_user
from ..core.security import create_access_token, hash_password, verify_password
from ..database import get_db
from ..models import CreditsLedger, User
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..services.configs import load_pricing

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    if len(data.password.encode("utf-8")) > 72:
        raise HTTPException(400, "密码 UTF-8 编码不能超过 72 字节")
    exists = await db.scalar(select(User).where(User.username == data.username))
    if exists:
        raise HTTPException(400, "用户名已存在")
    u = User(username=data.username, password_hash=hash_password(data.password), version="business")
    db.add(u)
    await db.flush()
    free = load_pricing().get("defaults", {}).get("free_quota", 0) or 0
    if free:
        u.credits_balance = free
        db.add(CreditsLedger(user_id=u.id, delta=free, reason="bonus"))
    await db.commit()
    await db.refresh(u)
    return UserOut.model_validate(u)


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    u = await db.scalar(select(User).where(User.username == data.username))
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return TokenOut(user=UserOut.model_validate(u), token=create_access_token(str(u.id)))


@router.get("/me", response_model=UserOut)
async def me(u: User = Depends(get_current_user)):
    return UserOut.model_validate(u)
