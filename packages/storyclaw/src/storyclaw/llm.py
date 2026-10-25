"""LLM 适配层：三种格式（openai_chat / anthropic / openai_responses）客户端构建 + 工厂注入。

agent 节点统一通过 `get_llm(model_choice)` 获取 (chat_model, model_id)：
1. 优先使用 backend 注入的 llm_factory（可查库 / 解密 key / 按版本路由）；
2. 兼容旧接口 set_llm_factory；
3. 兜底：环境变量 LLM_DEFAULT_* 直接构建。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from .config import settings
from .deps import get_deps

log = logging.getLogger("storyclaw.llm")

# 兼容旧接口（早期 set_llm_factory 注入方式）
_LLM_FACTORY: Optional[Callable[[dict], Any]] = None


def set_llm_factory(factory: Optional[Callable[[dict], Any]]) -> None:
    """（兼容）设置 LLM 工厂；新代码请使用 deps.configure(llm_factory=...)."""
    global _LLM_FACTORY
    _LLM_FACTORY = factory


async def get_llm(model_choice: dict | None = None):
    """返回 (chat_model, model_id)。"""
    mc = model_choice or {}
    deps = get_deps()
    if deps.llm_factory is not None:
        return await deps.llm_factory(mc)
    if _LLM_FACTORY is not None:
        return await _LLM_FACTORY(mc)
    return _build_env_default(mc)


def build_chat_client(
    *,
    format: str,
    model: str,
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.7,
    max_tokens: int = 8192,
    extra_body: dict | None = None,
):
    """按格式构建 chat client。

    支持三种格式（models.yaml 的 format 字段）：
    - openai_chat:     langchain_openai.ChatOpenAI（GPT / vLLM / Ollama / DeepSeek / 通义等）
    - anthropic:       langchain_anthropic.ChatAnthropic（Claude）
    - openai_responses: OpenAI Responses API（OpenAI 新版接口）
    """
    fmt = (format or "openai_chat").lower()
    if fmt == "anthropic":
        from langchain_anthropic import ChatAnthropic
        kw: dict = {
            "model": model, "api_key": api_key or "x",
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if base_url:
            kw["anthropic_api_url"] = base_url
        return ChatAnthropic(**kw)
    if fmt == "openai_responses":
        return _build_responses(model, api_key, base_url, temperature, max_tokens)
    # openai_chat（默认）
    from langchain_openai import ChatOpenAI
    kw = {
        "model": model, "api_key": api_key or "dummy",
        "temperature": temperature, "max_tokens": max_tokens,
    }
    if base_url:
        kw["base_url"] = base_url
    if extra_body:
        kw["extra_body"] = extra_body
    return ChatOpenAI(**kw)


def _build_responses(model: str, api_key: str, base_url: str, temperature: float, max_tokens: int):
    """OpenAI Responses API 适配。

    langchain 生态暂无开箱即用的 Responses 客户端，这里提供两种路径：
    - 若 base_url 指向 OpenAI 官方 /v1，使用自定义 `ResponsesChatModel`（BaseChatModel 包装 /v1/responses）；
    - 其它 OpenAI 兼容端点（如阿里云 compatible-mode）走 ChatOpenAI（/chat/completions）。
    默认回退 ChatOpenAI 以保证不中断；接入真实 Responses 端点时启用 ResponsesChatModel。
    """
    if not base_url and "openai.com" in (base_url or ""):
        # 官方 OpenAI 端点 → 使用 /v1/responses 包装
        try:
            from .responses_model import ResponsesChatModel
            return ResponsesChatModel(
                model=model, api_key=api_key or "dummy",
                base_url=base_url or "https://api.openai.com/v1",
                temperature=temperature, max_tokens=max_tokens,
            )
        except Exception as e:  # pragma: no cover
            log.warning("ResponsesChatModel 不可用，回退 ChatOpenAI: %s", e)
    from langchain_openai import ChatOpenAI
    kw = {
        "model": model, "api_key": api_key or "dummy",
        "temperature": temperature, "max_tokens": max_tokens,
    }
    if base_url:
        kw["base_url"] = base_url
    return ChatOpenAI(**kw)


def _build_env_default(model_choice: dict):
    """兜底：环境变量直接构建（本地开发 / 未注入工厂时）。"""
    import os
    key = settings.llm_default_api_key or os.getenv("OPENAI_API_KEY", "")
    model = model_choice.get("model_id") or settings.llm_default_model
    return (
        build_chat_client(
            format="openai_chat", model=model, api_key=key,
            base_url=settings.llm_default_base_url,
        ),
        model,
    )
