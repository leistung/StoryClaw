"""LLM 工厂（backend 数据层）：把 DB 配置解析成 agent 可用的 chat client。

client 构建（三种格式适配：openai_chat / anthropic / openai_responses）
统一在 backend/packages/harness/storyclaw/models/llm.py；
本模块只负责：解析平台配置 / 解密 key / 路由模型 → 调 storyclaw.llm.build_chat_client。
"""
from __future__ import annotations

from app.config import settings
from app.core.security import decrypt_api_key
from app.services.platform.configs import load_models

def build_chat_client(*, format: str, model: str, api_key: str = "", base_url: str = "",
                      temperature: float = 0.7, max_tokens: int = 8192, extra_body: dict | None = None):
    """委托 storyclaw.llm.build_chat_client（格式适配统一在 agent 包）。"""
    from storyclaw.models.llm import build_chat_client as _build
    return _build(format=format, model=model, api_key=api_key, base_url=base_url,
                  temperature=temperature, max_tokens=max_tokens, extra_body=extra_body)


def _build_business(model_id: str):
    m = next((x for x in load_models().get("models", []) if x.get("id") == model_id), None)
    if not m or not m.get("enabled") or model_id == "custom-local":
        raise ValueError(f"未知模型 {model_id}")
    from app.services.platform.pricing import get_model_pricing
    price = get_model_pricing(model_id)
    if not price or not price.get("enabled", True):
        raise ValueError("该模型尚未配置积分价格或已停用")
    key = decrypt_api_key(m.get("api_key_enc")) or (settings.anthropic_api_key if m["format"] == "anthropic" else settings.openai_api_key)
    remote_model = m.get("model") or model_id
    if m["format"] == "anthropic":
        return build_chat_client(format="anthropic", model=remote_model, api_key=key, base_url=m.get("base_url", "")), model_id
    return build_chat_client(
        format=m.get("format", "openai_chat"), model=remote_model,
        api_key=key, base_url=m.get("base_url", ""),
        extra_body={"thinking": {"type": m["thinking"]}} if m.get("thinking") else None,
    ), model_id


# ===== P0-4: LLM 工厂（供 storyclaw 包注入） =====

async def build_llm_from_choice(model_choice: dict) -> tuple:
    """供 storyclaw.configure(llm_factory=...) 注入的异步工厂。

    model_choice:
      - {"kind":"business","model_id":"gpt-4o-mini"}

    返回 (chat_model, model_id)。
    """
    kind = model_choice.get("kind") or "business"
    if kind == "business":
        model_id = model_choice.get("model_id") or next((m["id"] for m in load_models().get("models", []) if m.get("enabled") and m["id"] != "custom-local"), "")
        models = load_models().get("models", [])
        selected = next((m for m in models if m.get("id") == model_id), {})
        fallbacks = selected.get("fallback_models", [])
        if fallbacks:
            from storyclaw.models.fallback import QuotaFallbackModel
            ids = list(dict.fromkeys([model_id, *fallbacks]))[:2]
            if any(not any(m.get("id") == ident and m.get("enabled") for m in models) for ident in ids):
                raise ValueError("降级模型不存在或未启用")
            return QuotaFallbackModel([(lambda ident=ident: _build_business(ident)[0], ident) for ident in ids]), model_id
        return _build_business(model_id)
    raise ValueError("仅支持平台模型")
