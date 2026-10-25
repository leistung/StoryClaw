"""统一平台 Embedding 配置，不从用户个人模型配置读取。"""
from ..core.security import decrypt_api_key
from .configs import _load

def set_embedding_user(user_id):
    pass  # 保留旧调用兼容；平台配置按服务统一，检索仍须按用户与作品隔离。

async def resolve_embedding_config():
    cfg = _load("embedding.yaml")
    if not cfg.get("model"):
        return None
    key = decrypt_api_key(cfg.get("api_key_enc")) or ""
    return {"model": cfg["model"], "base_url": cfg.get("base_url", ""), "api_key": key, "dimensions": cfg.get("dimensions")}
