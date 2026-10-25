"""大纲规划子图：LLM 生成 + 模板兜底。

独立成模块，避免 graph.py 与 analyst.py 循环引用。
"""
from __future__ import annotations

from typing import Any

from ._util import llm_respond
from .prompts import SYSTEM_OUTLINE, build_outline_user_prompt


def mock_outline(meta: dict) -> dict:
    total = int(meta.get("target_chapters", 20) or 20)
    per_vol = 7
    volumes: list[dict[str, Any]] = []
    ch = 1
    vn = 0
    while ch <= total:
        vn += 1
        end = min(ch + per_vol - 1, total)
        chapters = [
            {"number": n, "title": f"第{n}章 待定", "summary": "（待生成梗概）"}
            for n in range(ch, end + 1)
        ]
        volumes.append({"name": f"第{vn}卷", "chapters": chapters})
        ch = end + 1
    return {"volumes": volumes}


def validate_outline(outline: dict, total: int) -> None:
    if not isinstance(outline, dict) or not isinstance(outline.get("volumes"), list):
        raise ValueError("大纲缺少 volumes")
    chapters = [c for v in outline["volumes"] for c in v.get("chapters", [])]
    if [c.get("number") for c in chapters] != list(range(1, total + 1)):
        raise ValueError(f"章号必须连续且恰好为 1 到 {total}")
    for ch in chapters:
        if not ch.get("title") or not ch.get("summary") or any(x in ch["title"] for x in ("待定", "待生成")):
            raise ValueError("大纲含空标题、空梗概或占位内容")


async def plan_outline(state: dict[str, Any]) -> dict:
    """大纲规划节点：优先 LLM 生成，失败回退模板。"""
    meta = state.get("book_meta", {})
    try:
        import json
        if meta.get('planning_mode')=='serial':
            from .serial import generate_framework
            return {'outline':await generate_framework(meta),'error':None}
        total = int(meta.get("target_chapters", 20))
        if not 1 <= total <= 500:
            raise ValueError("章数须在 1 到 500 之间")
        outline = {"volumes": []}
        # Long outlines are produced in bounded batches. Completed batches stay in
        # memory only; an invalid later batch never overwrites the saved outline.
        for first in range(1, total + 1, 10):
            last = min(first + 9, total)
            previous = json.dumps(outline, ensure_ascii=False)
            prompt = build_outline_user_prompt(meta) + (
                f"\n本次仅生成第 {first} 到 {last} 章，恰好 {last-first+1} 章，"
                "保持全书章号，输出一个卷的 volumes JSON。每章梗概不超过50字。"
                "不要在本批提前结束全书；结局只放在全书最后一章。"
                f"\n此前已确定大纲（不得重复）：{previous}"
            )
            error = None
            for attempt in range(2):
                content, _, _, _ = await llm_respond(
                    {"model_choice": None}, SYSTEM_OUTLINE,
                    prompt + (f"\n上次校验失败：{error}。重新输出本批完整严格JSON。" if error else ""),
                )
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                try:
                    batch = json.loads(content)
                    chapters = [c for v in batch["volumes"] for c in v.get("chapters", [])]
                    if [c.get("number") for c in chapters] != list(range(first, last + 1)):
                        raise ValueError(f"本批章号必须恰好为 {first} 到 {last}")
                    validate_outline({"volumes": [{"chapters": [dict(c, number=i+1) for i,c in enumerate(chapters)]}]}, len(chapters))
                    break
                except (ValueError, KeyError, TypeError) as exc:
                    error = str(exc)
                    if attempt == 1:
                        raise ValueError(f"第{first}-{last}章大纲校验失败：{error}") from exc
            if first==1 and isinstance(batch.get("overview"),str):outline["overview"]=batch["overview"]
            outline["volumes"].extend(batch["volumes"])
        validate_outline(outline, total)
        return {"outline": outline, "error": None}
    except Exception as e:
        return {"outline": mock_outline(meta), "error": f"LLM 不可用，使用模板大纲: {e}"}


async def generate_outline(meta):
    from .graph import outline_graph
    result=await outline_graph.ainvoke({'book_meta':meta})
    if result.get('error'):raise ValueError('大纲未通过校验，未覆盖已有内容：'+result['error'])
    outline=result.get('outline') or {}
    if not outline:raise ValueError('未返回大纲')
    return outline,None


def validate_confirmation(content):
    if content.get('planning_mode')=='serial':
        from .serial import Framework
        Framework.model_validate(content)
        return
    volumes=content.get('volumes')
    if not isinstance(volumes,list) or not volumes:raise ValueError('至少需要一个卷和章节规划')
    if any(not isinstance(v,dict) or not isinstance(v.get('chapters'),list) for v in volumes):raise ValueError('卷和章节结构无效')
    chapters=[c for v in volumes for c in v['chapters']]
    if not chapters or any(not isinstance(c,dict) for c in chapters):raise ValueError('请添加章节规划')
    validate_outline(content,len(chapters))
