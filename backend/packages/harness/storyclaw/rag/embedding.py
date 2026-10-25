"""Embedding 服务：调用 OpenAI 兼容 /v1/embeddings 接口。

支持批量嵌入（最多 25 条/请求）。
配置优先级：
  1. 显式传入 cfg
  2. backend 注入的 embedding_resolver（可查用户默认 LLM 配置）
  3. 环境变量 LLM_DEFAULT_BASE_URL / LLM_DEFAULT_API_KEY / EMBEDDING_MODEL
  4. 内置兜底：dashscope text-embedding-v3
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from storyclaw.config.settings import settings
from storyclaw.runtime.deps import get_deps

_FALLBACK_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_FALLBACK_MODEL = "text-embedding-v3"


def _resolve_config_from_env() -> dict[str, str] | None:
    base_url = os.getenv("LLM_DEFAULT_BASE_URL", "").strip()
    api_key = os.getenv("LLM_DEFAULT_API_KEY", "").strip()
    if not api_key:
        api_key = settings.llm_default_api_key or ""
    if not base_url or not api_key:
        return None
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": os.getenv("EMBEDDING_MODEL", "").strip() or _FALLBACK_MODEL,
    }


async def _resolve_config_async(cfg: dict | None = None, skip_env: bool = False) -> dict[str, str]:
    """异步解析配置：cfg > backend resolver > env > 兜底。

    skip_env=True（hash 模式）：只认显式 cfg 或用户 resolver 的配置，
    忽略环境变量 LLM_DEFAULT_*（避免开发机上的对话 key 被误当作 embedding 端点）。
    """
    if cfg:
        return cfg
    resolver = get_deps().embedding_resolver
    if resolver is not None:
        try:
            db_cfg = await resolver()
            if db_cfg and db_cfg.get("api_key") and db_cfg.get("base_url"):
                return db_cfg
        except Exception:
            pass
    if skip_env:
        return {"base_url": "", "api_key": "", "model": ""}
    env_cfg = _resolve_config_from_env()
    if env_cfg and env_cfg["api_key"]:
        return env_cfg
    return {
        "base_url": _FALLBACK_BASE_URL,
        "api_key": "",
        "model": _FALLBACK_MODEL,
    }


async def embed_texts(texts: list[str], cfg: dict | None = None) -> list[list[float]]:
    # 配置解析：hash 模式只认用户显式配置的 embedding（有 api_key 才走真实调用），
    # 用户未配置时用内置伪向量兜底（开发/测试），避免被环境里的对话 LLM key 抢占。
    mode = os.getenv("EMBEDDING_MODE", "").strip().lower()
    if mode in {"hash", "dummy"}:
        c = await _resolve_config_async(cfg, skip_env=True)
        if not c.get("api_key"):
            return [_hash_vector(t, settings.milvus_dim) for t in texts]
    else:
        c = await _resolve_config_async(cfg)

    if not c["api_key"]:
        raise ValueError("Embedding API key 未配置（LLM_DEFAULT_API_KEY 或 用户默认 LLM 配置）")
    results: list[list[float]] = []
    batch_size = 25
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            payload = {"model": c["model"], "input": batch, "encoding_format": "float"}
            if c.get("dimensions") is not None:
                payload["dimensions"] = c["dimensions"]
            from storyclaw.models.metering import active_meter
            meter=active_meter.get();call=None;data={};complete=False
            if meter:
                call=await meter.reserve('embedding:'+c['model'],sum(len(t.encode()) for t in batch),0);meter.call_ids.append(call)
            try:
                resp = await client.post(
                    f"{c['base_url']}/embeddings",
                    headers={"Authorization": f"Bearer {c['api_key']}", "Content-Type": "application/json"},
                    json=payload,
                )
                if resp.status_code==200:data=resp.json();complete=True
            finally:
                if meter and call:
                    tokens=(data.get('usage') or {}).get('total_tokens')
                    usage={'input_tokens':tokens,'output_tokens':0} if tokens is not None else {}
                    meter.spent+=await meter.settle(call,usage,complete);meter.calls+=1
            if resp.status_code != 200:
                raise ValueError(f"Embedding API 调用失败 {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda item: item["index"])
            if [item["index"] for item in items] != list(range(len(batch))):
                raise ValueError("Embedding 返回数量或索引不匹配")
            import math
            for item in items:
                vector = item["embedding"]
                if len(vector) != settings.milvus_dim or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
                    raise ValueError(f"Embedding 维度必须为 {settings.milvus_dim}，且数值必须有效；更换模型需重建索引")
                results.append(vector)
    return results


def _hash_vector(text: str, dim: int = 1024) -> list[float]:
    """确定性伪向量：CJK 双字 + 英文 token 的词袋哈希，L2 归一化。

    用于 EMBEDDING_MODE=hash（开发/测试），保证同一 token 得到同一向量，
    词重合越多 cosine 相似度越高。
    """
    import hashlib
    import math
    import re

    tokens: list[str] = []
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend("".join(cjk[i:i + 2]) for i in range(len(cjk) - 1))
    tokens.extend(re.findall(r"[a-zA-Z0-9_]{2,}", text.lower()))
    if not tokens:
        tokens = [text[:4]]

    vec = [0.0] * dim
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


async def embed_query(text: str, cfg: dict | None = None) -> list[float]:
    vecs = await embed_texts([text], cfg)
    return vecs[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """内存 cosine 相似度（降级存储用）。"""
    import math
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
