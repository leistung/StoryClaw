from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models import User
from app.services.platform.configs import load_models
from app.services.platform.configs import load_pricing

router = APIRouter(prefix="", tags=["configs"])


@router.get("/models")
async def list_models(u: User = Depends(get_current_user)):
    data = load_models()
    return [{k: v for k, v in m.items() if k not in {"api_key", "api_key_enc"}}
            for m in data.get("models", []) if m.get("enabled") and m.get("id") != "custom-local"]


@router.get("/pricing")
async def get_pricing(u: User = Depends(get_current_user)):
    return load_pricing()


@router.get("/model-status")
async def model_status(u: User = Depends(get_current_user)):
    import os
    from app.config import settings
    from app.services.platform.configs import _load
    catalog = load_models().get("models", [])
    prices = load_pricing().get("pricing", {})
    chat = any(m.get("enabled") and m.get("id") != "custom-local" and prices.get(m["id"], {}).get("enabled", True)
        and m["id"] in prices and (m.get("api_key_enc") or (settings.anthropic_api_key if m.get("format") == "anthropic" else settings.openai_api_key)) for m in catalog)
    emb = _load("embedding.yaml")
    embedding = bool(emb.get("model") and emb.get("api_key_enc")) if emb else bool(os.getenv("LLM_DEFAULT_API_KEY"))
    return {"chat": bool(chat), "embedding": embedding}
