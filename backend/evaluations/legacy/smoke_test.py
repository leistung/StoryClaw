#!/usr/bin/env python3
"""StoryClaw 端到端冒烟测试（需 backend 已通过 docker compose 启动）。

覆盖：注册/登录（local+business）、LLM 配置、建书、大纲生成、章节生成（真实 agent 写路径）、
章节入库（Milvus+Neo4j）、RAG 混合检索、RAG 状态、Ask 对话、Skill 列表、商业积分扣减、充值信息。

用法：
  PYTHONPATH=backend:backend/packages/harness .venv/bin/python backend/evaluations/legacy/smoke_test.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = os.environ.get("STORYCLAW_BASE", "http://localhost:8000/api")
PASS, FAIL = [], []


def check(name: str, cond: bool, extra: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


def read_env():
    env = {}
    p = Path(__file__).resolve().parents[3] / ".env"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main():
    env = read_env()
    root = BASE.rsplit("/api", 1)[0] + "/"
    c = httpx.Client(timeout=300, base_url=BASE)

    print(f"BASE = {BASE}")
    try:
        r = httpx.get(root + "health", timeout=10)
        check("GET /health", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        print("!! backend 未就绪:", e)
        sys.exit(1)

    suffix = uuid.uuid4().hex[:6]

    # ---------- 本地版用户 ----------
    local_name = f"local_{suffix}"
    r = c.post("/auth/register", json={"username": local_name, "password": "test123456", "version": "local"})
    check("注册 local 用户", r.status_code == 200, r.text[:120])
    if r.status_code != 200:
        sys.exit(1)
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    r = c.get("/auth/me", headers=h)
    me = r.json()
    check("GET /me (local)", r.status_code == 200 and me["version"] == "local", f"id={me['id']}")

    # 创建 LLM 配置（指向环境变量里的阿里云 MaaS）
    llm_cfg = {
        "name": "aliyun-qwen",
        "format": "openai_chat",
        "base_url": env.get("LLM_DEFAULT_BASE_URL", ""),
        "model": env.get("LLM_DEFAULT_MODEL", "qwen3.7-flash"),
        "api_key": env.get("LLM_DEFAULT_API_KEY", ""),
        "temperature": 0.7,
        "max_tokens": 2048,
        "is_default": True,
    }
    r = c.post("/llm-configs", json=llm_cfg, headers=h)
    check("创建 LLM 配置", r.status_code == 200, r.text[:120])
    cfg_id = r.json().get("id")

    # 建书
    book = {
        "title": f"测试之书 {suffix}",
        "intro": "一个用于端到端冒烟测试的故事。",
        "genre": "玄幻",
        "platforms": ["起点", "番茄"],
        "target_chapters": 3,
        "target_words": 9000,
        "per_chapter_words": 1200,
        "protagonist_name": "阿澈",
        "protagonist_intro": "身怀异能的少年。",
    }
    r = c.post("/books", json=book, headers=h)
    check("创建书籍", r.status_code == 200, r.text[:120])
    bid = r.json()["id"]

    # 大纲生成（真实 LLM，outline_graph）
    r = c.post(f"/books/{bid}/outline/generate", json={}, headers=h)
    out = r.json()
    ok = r.status_code == 200 and (out.get("content") or out.get("error") is None)
    check("生成大纲（outline agent）", r.status_code == 200, r.text[:200])
    if out.get("content"):
        chs = out["content"].get("chapters", [])
        print(f"      大纲章节数: {len(chs)}")

    # 建章节
    r = c.post(f"/chapters/books/{bid}", json={"title": "第一章 觉醒"}, headers=h)
    check("创建章节", r.status_code == 200, r.text[:120])
    cid = r.json()["id"]

    # 生成章节内容（真实 agent 写路径）
    r = c.post(f"/chapters/{cid}/generate", json={"llm_choice": {"kind": "local", "config_id": cfg_id, "user_id": me["id"]}}, headers=h)
    gen = r.json()
    check("生成章节（write agent）", r.status_code == 200 and gen.get("content"), r.text[:200])
    if gen.get("content"):
        print(f"      章节字数: {gen.get('word_count')} | model={gen.get('model')} | in={gen.get('in_tokens')} out={gen.get('out_tokens')}")

    # 章节入库 → Milvus + Neo4j
    r = c.post(f"/chapters/{cid}/ingest", json={}, headers=h)
    ing = r.json()
    check("章节入库（ingest）", r.status_code == 200, r.text[:200])
    if ing:
        print(f"      chunks={ing.get('chunks')} entities={ing.get('entities')} relations={ing.get('relations')} rag_status={ing.get('rag_status')} error={ing.get('error')}")

    # RAG 检索（用生成正文的片段作查询词，保证命中）
    _q = gen.get("content", "")
    query_text = _q[:20] if len(_q) >= 20 else "阿澈 觉醒 能力"
    r = c.post("/rag/query", json={"book_id": bid, "query": query_text, "top_k": 3}, headers=h)
    q = r.json()
    check("RAG 混合检索", r.status_code == 200 and isinstance(q.get("chunks"), list), r.text[:200])
    if q:
        print(f"      query={query_text!r}")
        print(f"      chunks={len(q.get('chunks', []))} entities={len(q.get('entities', []))} relations={len(q.get('relations', []))}")

    # RAG 状态
    r = c.get(f"/books/{bid}/rag-status", headers=h)
    st = r.json()
    check("RAG 状态", r.status_code == 200 and isinstance(st.get("chapters"), list), r.text[:200])
    if st:
        print(f"      total_chunks={st.get('total_chunks')} total_entities={st.get('total_entities')}")

    # 配置实体 + rag-related
    r = c.post(f"/books/{bid}/config/character", json={"name": "阿澈", "category": "主角", "description": "测试主角", "kv": [{"key": "性格", "value": "坚韧"}]}, headers=h)
    check("创建角色配置实体", r.status_code == 200, r.text[:120])
    if r.status_code == 200:
        eid = r.json()["id"]
        r2 = c.get(f"/books/{bid}/config/character/{eid}/rag-related", headers=h)
        check("角色 rag-related", r2.status_code == 200, r2.text[:160])

    # Ask 对话（agent loop）
    r = c.post("/chat", json={"message": "用一句话介绍这本书的主角阿澈的性格设定。", "llm_choice": {"kind": "local", "config_id": cfg_id, "user_id": me["id"]}}, headers=h)
    ch = r.json()
    check("Ask 对话（agent loop）", r.status_code == 200 and bool(ch.get("content")), r.text[:200])
    if ch.get("content"):
        print(f"      reply={ch['content'][:60]!r}... model={ch.get('model')} in={ch.get('in_tokens')} out={ch.get('out_tokens')}")

    # Skill 列表
    r = c.get("/skills", headers=h)
    sk = r.json()
    check("Skill 列表", r.status_code == 200 and isinstance(sk, list) and len(sk) > 0, f"count={len(sk) if isinstance(sk, list) else '?'}")
    if isinstance(sk, list):
        names = [s.get("name") for s in sk[:5]]
        print(f"      skills: {names}")

    # ---------- 商业版用户 ----------
    biz_name = f"biz_{suffix}"
    r = c.post("/auth/register", json={"username": biz_name, "password": "test123456", "version": "business"})
    check("注册 business 用户", r.status_code == 200, r.text[:120])
    if r.status_code == 200:
        bh = {"Authorization": f"Bearer {r.json()['token']}"}
        r = c.get("/auth/me", headers=bh)
        bme = r.json()
        check("GET /me (business 含积分)", r.status_code == 200 and bme["version"] == "business", f"credits={bme.get('credits_balance')}")
        r = c.get("/recharge/memberships", headers=bh)
        mj = r.json() if r.status_code == 200 else {}
        check("充值会员列表", r.status_code == 200 and isinstance(mj.get("memberships"), list) and len(mj.get("memberships", [])) > 0, r.text[:120])
        # 商业版 LLM 调用（可能因外部 key 无效而失败 —— 单独记录，不判 FAIL）
        r = c.post("/chat", json={"message": "你好", "llm_choice": {"kind": "business", "model_id": "gpt-4o-mini"}}, headers=bh)
        if r.status_code == 200:
            j = r.json()
            check("商业版 Ask（真实扣积分）", j.get("credits_cost", 0) > 0, f"credits_cost={j.get('credits_cost')}")
            r2 = c.get("/me", headers=bh)
            check("商业版积分已扣减", r2.json().get("credits_balance", -1) < bme.get("credits_balance", 0), f"before={bme.get('credits_balance')} after={r2.json().get('credits_balance')}")
        else:
            print(f"  [!] 商业版 Ask 未跑通（外部模型 key/网络限制，非代码缺陷）: {r.text[:200]}")

    print("\n==================== 结果汇总 ====================")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    for x in PASS:
        print(f"  + {x}")
    for x in FAIL:
        print(f"  - {x}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
