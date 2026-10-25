#!/usr/bin/env python3
"""StoryClaw 端到端测试脚本：用指定账号生成一本书的全部内容。

流程：登录 → 创建书籍 → 生成大纲(LangGraph) → 批量写章节(Agent) → 逐章入库(RAG: Milvus+Neo4j) → 汇总状态。

用法：
    python3 scripts/test_generate_book.py                # 默认 local_17c707 / test123456 / 3 章
    python3 scripts/test_generate_book.py <用户名> <密码> [章节数]

依赖：仅 Python 标准库（urllib）。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api/v1"
TITLE_PREFIX = "自动化测试"


def req(method: str, path: str, token: str | None = None, body: dict | None = None, timeout: int = 300):
    """发起请求，返回 (status, json)。HTTP 错误也返回解析后的响应体。"""
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


def step(title: str):
    print(f"\n{'=' * 64}\n▶ {title}\n{'=' * 64}")


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else "local_17c707"
    password = sys.argv[2] if len(sys.argv) > 2 else "test123456"
    chapters = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    print(f"账号: {username} | 计划生成章节数: {chapters}\n")

    # ---- 1. 登录 ----
    step("1/6 登录")
    st, data = req("POST", "/auth/login", body={"username": username, "password": password}, timeout=30)
    if st != 200:
        print(f"❌ 登录失败: {st} {data}")
        sys.exit(1)
    token = data["token"]
    user = data["user"]
    print(f"✅ 登录成功 user_id={user['id']} version={user['version']}")

    # ---- 2. 创建书籍 ----
    step("2/6 创建书籍")
    ts = time.strftime("%m%d%H%M%S")
    book_body = {
        "title": f"{TITLE_PREFIX}-{ts}",
        "intro": "自动化端到端测试生成的小说：主角在异界觉醒，踏上修炼之路。",
        "genre": "玄幻",
        "platforms": ["起点"],
        "target_chapters": chapters,
        "target_words": chapters * 3000,
        "per_chapter_words": 3000,
        "protagonist_name": "林尘",
        "protagonist_intro": "少年林尘，身负神秘剑骨，性格坚毅，誓要守护家人。",
    }
    st, book = req("POST", "/books", token, book_body)
    if st != 200:
        print(f"❌ 创建书籍失败: {st} {data}")
        sys.exit(1)
    bid = book["id"]
    print(f"✅ 创建书籍成功 id={bid} 「{book['title']}」")

    # ---- 3. 生成大纲 ----
    step("3/6 生成大纲 (LangGraph outline_graph)")
    t0 = time.time()
    st, outline = req("POST", f"/books/{bid}/outline/generate", token, timeout=300)
    if st != 200:
        print(f"⚠️ 大纲生成失败: {st} {outline}")
        outline_content = {}
    else:
        outline_content = outline.get("content") or {}
        n_vol = len(outline_content.get("volumes") or [])
        n_ch = sum(len(v.get("chapters") or []) for v in outline_content.get("volumes") or [])
        print(f"✅ 大纲生成完成 ({time.time()-t0:.0f}s) 卷数={n_vol} 章节数={n_ch}")

    # ---- 4. 批量写章节 ----
    step(f"4/6 批量写 {chapters} 章 (Agent graph: writer→reviewer)")
    t0 = time.time()
    st, mw = req(
        "POST",
        f"/books/{bid}/multi-write",
        token,
        body={"start_number": 1, "end_number": chapters, "skip_existing": False},
        timeout=600,
    )
    if st != 200:
        print(f"❌ 批量写作失败: {st} {mw}")
        sys.exit(1)
    items = mw.get("chapters") or []
    ok = [i for i in items if i.get("status") == "generated"]
    failed = [i for i in items if i.get("status") != "generated"]
    print(f"✅ 批量写作完成 ({time.time()-t0:.0f}s) 成功={len(ok)} 失败={len(failed)}")
    total_words = 0
    for i in ok:
        total_words += i.get("word_count") or 0
        print(f"   · 第{i.get('number')}章 「{i.get('title')}」 {i.get('word_count')} 字")
    for i in failed:
        print(f"   ❌ 第{i.get('number')}章 失败: {i.get('error')}")

    # ---- 5. 逐章入库 RAG ----
    step("5/6 逐章入库 RAG (Milvus 向量 + Neo4j 图谱)")
    chapter_ids = {i.get("number"): i.get("chapter_id") for i in ok}
    total_chunks, total_entities, total_relations = 0, 0, 0
    for num in sorted(chapter_ids):
        cid = chapter_ids[num]
        st, ing = req("POST", f"/chapters/{cid}/ingest", token, timeout=300)
        if st == 200:
            total_chunks += ing.get("chunks") or 0
            total_entities += ing.get("entities") or 0
            total_relations += ing.get("relations") or 0
            print(f"   ✅ 第{num}章 入库成功 chunks={ing.get('chunks')} entities={ing.get('entities')} relations={ing.get('relations')} status={ing.get('rag_status')}")
        else:
            print(f"   ❌ 第{num}章 入库失败: {st} {ing}")

    # ---- 6. 汇总 ----
    step("6/6 汇总")
    st, status = req("GET", f"/books/{bid}/rag-status", token)
    print(f"书籍 id={bid} 总字数={total_words}")
    print(f"入库统计: chunks={total_chunks} entities={total_entities} relations={total_relations}")
    if st == 200:
        print(f"RAG 状态: {json.dumps(status, ensure_ascii=False)[:300]}")
    print(f"\n✅ 端到端测试完成。书籍工作区: http://localhost:5173/workspace/{bid}")


if __name__ == "__main__":
    main()
