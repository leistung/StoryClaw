from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    sub = decode_token(token)
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效凭证", headers={"WWW-Authenticate": "Bearer"})
    try:
        uid = int(sub)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效凭证")
    u = await db.get(User, uid)
    if not u:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    from ..services.platform import refresh_configs
    await refresh_configs(db)
    # 供请求日志中间件 / 可观测性使用
    request.scope["user"] = u.id
    # 供 embedding 配置解析（RAG 向量化）定位当前用户
    try:
        from ..services.embedding_config import set_embedding_user
        set_embedding_user(u.id)
    except Exception:
        pass
    return u
