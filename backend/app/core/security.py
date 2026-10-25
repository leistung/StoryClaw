import base64
import hashlib
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


def _fernet_key() -> bytes:
    """从 jwt_secret 派生 Fernet 密钥(32 字节 url-safe)。"""
    return base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest())


def encrypt_api_key(key: str | None) -> str | None:
    if not key:
        return None
    return Fernet(_fernet_key()).encrypt(key.encode()).decode()


def decrypt_api_key(enc: str | None) -> str | None:
    if not enc:
        return None
    try:
        return Fernet(_fernet_key()).decrypt(enc.encode()).decode()
    except Exception:
        return None


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": subject, "exp": expire}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None
