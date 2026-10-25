"""Context Manager：token 预算估算与保护。

Agent 节点在调用 LLM 前，用本模块估算 system+user 的 token 占用，
避免超出模型 context_window 导致调用失败（商业级稳定性兜底）。

估算规则（无需 tiktoken，快速近似）：
- 中文字符 ≈ 1 token/字
- 其它字符 ≈ 4 字符/token

context_limit 来源优先级：model_choice["context_limit"] → deps 注入的 resolver → 默认 128k。
"""

from __future__ import annotations

import logging
from typing import Any

from storyclaw.runtime.deps import get_deps

logger = logging.getLogger("storyclaw.context.builder")

DEFAULT_CONTEXT_LIMIT = 128000
# 安全系数：预留一部分给模型自身（指令跟随、输出）
SAFETY_RATIO = 0.9


def estimate_tokens(*texts: str) -> int:
    """粗略估算多个文本的总 token 数。"""
    total = 0.0
    for t in texts:
        if not t:
            continue
        cn = sum(1 for c in t if "\u4e00" <= c <= "\u9fff")
        other = len(t) - cn
        total += cn + other / 4.0
    return int(total)


def resolve_context_limit(model_choice: dict | None = None) -> int:
    """解析模型上下文窗口上限。"""
    mc = model_choice or {}
    lim = mc.get("context_limit")
    if lim:
        try:
            return int(lim)
        except (TypeError, ValueError):
            pass
    resolver = get_deps().context_limit_resolver
    if resolver is not None:
        try:
            resolved = resolver(mc)
            if resolved:
                return int(resolved)
        except Exception as e:  # pragma: no cover
            logger.warning("context_limit_resolver failed: %s", e)
    return DEFAULT_CONTEXT_LIMIT


def context_budget(
    system_prompt: str,
    user_message: str,
    model_choice: dict | None = None,
) -> dict[str, int | bool]:
    """返回 {estimated, limit, within, available} 预算报告。"""
    limit = resolve_context_limit(model_choice)
    est = estimate_tokens(system_prompt, user_message)
    cap = int(limit * SAFETY_RATIO)
    return {
        "estimated": est,
        "limit": limit,
        "within": est <= cap,
        "available": max(0, cap - est),
    }


def trim_user_message(user_message: str, keep_ratio: float = 0.7) -> str:
    """保守裁剪：保留前 keep_ratio 内容，尾部加提示。用于预算超限兜底。"""
    if not user_message:
        return user_message
    keep = int(len(user_message) * keep_ratio)
    if keep >= len(user_message):
        return user_message
    return user_message[:keep] + "\n\n[系统提示：上下文超出模型预算，已截断以保证本次生成]"
