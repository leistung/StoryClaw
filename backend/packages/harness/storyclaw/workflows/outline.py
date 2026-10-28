"""大纲规划子图：LLM 生成 + 模板兜底。

独立成模块，避免 graph.py 与 analyst.py 循环引用。
"""
from __future__ import annotations

from typing import Any

from storyclaw.models.calls import llm_respond
from storyclaw.prompts.templates import SYSTEM_OUTLINE
from storyclaw.prompts.templates import build_outline_user_prompt
from storyclaw.skills.loader import method_instructions


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
            from storyclaw.workflows.serial import generate_framework
            return {'outline':await generate_framework(meta),'error':None}
        if meta.get('creation_plan'):
            return {'outline':await expand_fixed_outline(meta),'error':None}
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
                "保持全书章号，输出一个卷的 volumes JSON。每章梗概150到300字，包含目标、阻碍、行动、转折和接续点。"
                "不要在本批提前结束全书；结局只放在全书最后一章。"
                f"\n此前已确定大纲（不得重复）：{previous}"
            )
            error = None
            for attempt in range(2):
                content, _, _, _ = await llm_respond(
                    {"model_choice": None}, SYSTEM_OUTLINE + '\n' + method_instructions('framework-design'),
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
    from storyclaw.agents.graph import outline_graph
    result=await outline_graph.ainvoke({'book_meta':meta})
    if result.get('error'):raise ValueError('大纲未通过校验，未覆盖已有内容：'+result['error'])
    outline=result.get('outline') or {}
    if not outline:raise ValueError('未返回大纲')
    return outline,None


async def expand_fixed_outline(meta):
    import json
    from storyclaw.workflows.serial import expand_framework
    from storyclaw.models.calls import strip_code_fence
    from storyclaw.runtime.progress import progress
    total=int(meta.get('target_chapters') or 20)
    if not 1<=total<=500:raise ValueError('章数须在1到500之间')
    outline=await expand_framework(meta)
    count=len(outline['volumes'])
    if count>total:raise ValueError('计划卷数超过章节数，请减少卷数后确认')
    first=1
    for vi,volume in enumerate(outline['volumes']):
        end=first+total//count+(1 if vi<total%count else 0)-1
        for start in range(first,end+1,5):
            last=min(start+4,end)
            await progress('step.started','outline.chapters',label=f'展开{volume["name"]}第{start}–{last}章')
            raw,*_=await llm_respond({'model_choice':{'kind':'business'},'response_format':{'type':'json_object'},'response_max_tokens':8192},SYSTEM_OUTLINE+'\n'+method_instructions('plot-design'),
                json.dumps({'book':{k:v for k,v in meta.items() if k!='creation_plan'},'framework':outline,
                    'task':f'仅生成第{start}到{last}章，属于{volume["name"]}，遵守该卷goal和相邻卷衔接。每章summary写150到300字，包含目标、阻碍、行动、转折和结果。保持全书连续章号，不重演此前事件，只有第{total}章可收束全书。输出 {{"chapters":[{{"number":1,"title":"标题","summary":"详细章纲"}}]}}'},ensure_ascii=False))
            chapters=json.loads(strip_code_fence(raw)).get('chapters',[])
            if [c.get('number') for c in chapters]!=list(range(start,last+1)) or any(len(c.get('summary',''))<100 for c in chapters):
                raise ValueError(f'第{start}–{last}章数量或详细程度不符合计划，未采用完整大纲')
            volume['chapters'].extend(chapters)
            await progress('step.completed','outline.chapters',label=f'第{start}–{last}章已展开')
        first=end+1
    validate_outline(outline,total)
    return outline


def validate_confirmation(content):
    if content.get('planning_mode')=='serial':
        from storyclaw.workflows.serial import Framework
        Framework.model_validate(content)
        return
    volumes=content.get('volumes')
    if not isinstance(volumes,list) or not volumes:raise ValueError('至少需要一个卷和章节规划')
    if any(not isinstance(v,dict) or not isinstance(v.get('chapters'),list) for v in volumes):raise ValueError('卷和章节结构无效')
    chapters=[c for v in volumes for c in v['chapters']]
    if not chapters or any(not isinstance(c,dict) for c in chapters):raise ValueError('请添加章节规划')
    validate_outline(content,len(chapters))
