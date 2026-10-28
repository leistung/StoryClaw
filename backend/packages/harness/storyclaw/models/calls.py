"""Agent 内部公共工具。"""
from __future__ import annotations

import logging
import re
from typing import Any, Awaitable, Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from storyclaw.models.budget import context_budget
from storyclaw.models.budget import trim_user_message
from storyclaw.models.llm import get_llm

log = logging.getLogger(__name__)


async def llm_respond(state: dict[str, Any], system_prompt: str, user_message: str):
    """调用注入的 LLM（单轮 system+user），带上下文预算保护。

    Returns (content, in_tokens, out_tokens, model_id)。
    失败时抛出异常，由调用方包装为 error 状态。
    """
    mc = state.get("model_choice") or {}
    budget = context_budget(system_prompt, user_message, mc)
    if not budget["within"]:
        log.warning(
            "context over budget, trimming",
            extra={"data": {"estimated": budget["estimated"], "limit": budget["limit"]}},
        )
        user_message = trim_user_message(user_message)
    llm, model_id = await get_llm(mc)
    if state.get("response_max_tokens"):
        llm = llm.bind(max_tokens=int(state["response_max_tokens"]))
    if state.get("response_format"):
        llm = llm.bind(response_format=state["response_format"])
    conv = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    from storyclaw.runtime.progress import progress
    from uuid import uuid4
    import time
    call_id=str(uuid4());started=time.monotonic()
    await progress('step.started','model.call',call_id=call_id,label='请求创作模型',model=model_id,
                   input_chars=len(system_prompt)+len(user_message),max_tokens=state.get('response_max_tokens',8192))
    try:
        resp = await llm.ainvoke(conv)
    except Exception as exc:
        await progress('step.failed','model.call',call_id=call_id,error=str(exc)[:600])
        raise
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    in_t = int(usage.get("input_tokens", 0) or 0)
    out_t = int(usage.get("output_tokens", 0) or 0)
    await progress('step.completed','model.call',call_id=call_id,model=model_id,input_tokens=in_t,output_tokens=out_t,
                   output_chars=len(content),duration_ms=round((time.monotonic()-started)*1000))
    return content, in_t, out_t, (getattr(resp, "response_metadata", {}) or {}).get("storyclaw_model_id", model_id)


async def stream_llm_respond(
    state: dict[str, Any],
    system_prompt: str,
    user_message: str,
    on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
):
    """流式调用注入的 LLM：逐 token/chunk 回调 on_delta(text)，结束后返回全文与 usage。

    Returns (content, in_tokens, out_tokens, model_id)。
    - usage 优先取 stream chunk 携带的 usage_metadata（OpenAI 兼容流），
      拿不到时按字符数估算（汉字约 1 token/字，英文约 4 字符/token）。
    """
    mc = state.get("model_choice") or {}
    budget = context_budget(system_prompt, user_message, mc)
    if not budget["within"]:
        log.warning(
            "context over budget, trimming",
            extra={"data": {"estimated": budget["estimated"], "limit": budget["limit"]}},
        )
        user_message = trim_user_message(user_message)
    llm, model_id = await get_llm(mc)
    if state.get("response_max_tokens"):
        llm = llm.bind(max_tokens=int(state["response_max_tokens"]))
    if state.get("response_format"):
        llm = llm.bind(response_format=state["response_format"])
    conv = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    buf: list[str] = []
    in_t = out_t = 0
    async for chunk in llm.astream(conv):
        model_id = (getattr(chunk, "response_metadata", {}) or {}).get("storyclaw_model_id", model_id)
        piece = ""
        if isinstance(chunk, str):
            piece = chunk
        else:
            piece = getattr(chunk, "content", None) or ""
            if not isinstance(piece, str):
                piece = str(piece)
        if piece:
            buf.append(piece)
            if on_delta is not None:
                try:
                    await on_delta(piece)
                except Exception:  # 推送失败不应中断生成
                    pass
        um = getattr(chunk, "usage_metadata", None) or {}
        in_t = int(um.get("input_tokens", 0) or 0) or in_t
        out_t = int(um.get("output_tokens", 0) or 0) or out_t
    content = "".join(buf)
    if out_t <= 0:
        out_t = max(1, len(content))
    if in_t <= 0:
        in_t = max(1, len(system_prompt) + len(user_message))
    return content, in_t, out_t, model_id


# 句子结束符（中文 + 英文 + 省略号）
_SENT_END_RE = re.compile(r"(?<=[。！？；.!?])")
_EXTRA_SENT_END_RE = re.compile(r"(?<=[……—])")


def ensure_paragraphs(text: str, sentences_per_para: int = 3) -> str:
    """确保正文按「空行分段」组织：已有空行段落则保留，否则按句号切分成段。

    网文阅读体验需要短段落（每段 2~4 句，一段一意）。
    """
    if not text:
        return text
    t = text.strip()
    if not t:
        return t
    # 已有空行分隔（或显式换行段落），视为已分段
    if "\n\n" in t or "\r\n\r\n" in t:
        # 只把单换行收敛为段落内文本（保持空行结构）
        return t.replace("\r\n", "\n")
    # 去掉已有的单个换行，统一按句子重排
    flat = re.sub(r"\s*\n\s*", "", t)
    parts = _SENT_END_RE.split(flat)
    # 处理省略号/破折号结尾（中文常用……）
    if len(parts) <= 1:
        parts = _EXTRA_SENT_END_RE.split(flat)
    sentences = [p.strip() for p in parts if p.strip()]
    if len(sentences) <= 1:
        # 通篇没有句号（异常），按逗号兜底
        segs = [s.strip() for s in re.split(r"(?<=[，,、])", flat) if s.strip()]
        if len(segs) > 1:
            sentences = segs
    paras = ["".join(sentences[i:i + sentences_per_para]) for i in range(0, len(sentences), sentences_per_para)]
    return "\n\n".join(paras)


def usage_payload(model_id: str, in_t: int, out_t: int) -> dict:
    return {"in_tokens": in_t, "out_tokens": out_t, "model_id": model_id}


def strip_code_fence(text: str) -> str:
    """去除 ```json ... ``` 围栏。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return text
