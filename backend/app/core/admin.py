"""Admin 权限依赖."""
from fastapi import Depends, HTTPException
from app.core.deps import get_current_user
from app.models import User


async def get_admin_user(u: User = Depends(get_current_user)) -> User:
    if not u.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return u
