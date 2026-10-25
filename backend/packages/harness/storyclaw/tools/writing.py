"""Writer Tool Use：工具 schema 定义 + ReAct 循环执行器。

- `WRITER_TOOLS`：JSON function schema 列表，绑定到 LLM 供其自主决策。
- `tool_loop()`：ReAct 循环——LLM 决定调工具 → 经 deps.tool_executor（backend 实时查库/RAG）
  执行并把结果作为 ToolMessage 喂回，最多 MAX_ROUNDS 轮，直至 LLM 不再调工具。

工具执行器未注入（deps.tool_executor is None）时返回空，writer 回退全量预注入。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from storyclaw.runtime.deps import get_deps
from storyclaw.models.llm import get_llm
from storyclaw.skills.loader import describe_skill
from storyclaw.skills.loader import read_skill_doc

log = logging.getLogger("storyclaw.tools")

MAX_TOOL_ROUNDS = 3

WRITER_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_setting",
            "description": "查询本书的设定档案（角色/场景/物品/情节），可按类型与关键词过滤。用于保证人物性格、场景、道具、伏笔与既有设定一致，不写偏。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "enum": ["character", "scene", "item", "plot", "world"],
                        "description": "设定类型：角色/场景/物品/情节",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "可选关键词，按名称或描述过滤",
                    },
                },
                "required": ["entity_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_memory",
            "description": "在本书记忆库（向量+图谱）检索与关键词最相关的前文章节片段、实体与关系。用于回忆之前发生的情节、人物关系、伏笔，保持跨章连贯。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词/问题，如\"避难所\"\"苏槿与林夜的关系\"\"量子核心伏笔\""},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_outline",
            "description": "获取指定章节的大纲节点（梗概/要点），确认本章应推进的情节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_number": {"type": "integer", "description": "章节序号"},
                },
                "required": ["chapter_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prev_chapter",
            "description": "获取指定章节的上一章内容摘要，确保本章开头与上章结尾衔接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_number": {"type": "integer", "description": "本章章节序号（返回其前一章摘要）"},
                },
                "required": ["chapter_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_meta",
            "description": "获取本书元信息（书名/类型/简介/主角/目标字数），写作前了解全局设定。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def tool_loop(state: dict[str, Any], sys_prompt: str, user_msg: str) -> str:
    """ReAct 工具循环：返回收集到的工具结果摘要（空串 = 无工具/未注入）。

    state 需含 model_choice / user_id / book_id / chapter_id。
    """
    executor = get_deps().tool_executor
    if executor is None:
        return ""
    mc = state.get("model_choice") or {}
    user_id = state.get("user_id")
    book_id = state.get("book_id")
    chapter_id = state.get("chapter_id")
    try:
        llm, _model_id = await get_llm(mc)
        llm_tools = llm.bind_tools(WRITER_TOOLS).bind(max_tokens=512)
    except Exception as e:  # 模型不支持 tools 等
        log.warning("bind_tools failed, skip tool loop: %s", e)
        return ""

    conv: list[Any] = [
        SystemMessage(content=sys_prompt + "\n\n<tool_usage>写作前可调用工具获取必要信息（设定/记忆/大纲/前章）。"
                                          "先调用工具收集信息，本阶段只收集信息，不撰写正文；资料足够后回复“查询完毕”。</tool_usage>"),
        HumanMessage(content=user_msg),
    ]
    results: list[str] = []
    for _round in range(MAX_TOOL_ROUNDS):
        try:
            resp = await llm_tools.ainvoke(conv)
        except Exception as e:
            # An upstream failure is not evidence that context is sufficient.
            raise
        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            break
        conv.append(AIMessage(content=resp.content or "", tool_calls=tool_calls))
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args") or {}
            tid = tc.get("id", "")
            try:
                out = await executor(name, args, user_id, book_id, chapter_id)
            except Exception as e:  # noqa: BLE001
                out = f"工具 {name} 执行失败: {e}"
            conv.append(ToolMessage(content=out, tool_call_id=tid))
            results.append(f"### 工具 {name}({args})\n{out}")
            log.info("writer tool call name=%s args=%s", name, args)
    return "\n\n".join(results)


# ===== Skill 自主发现（DeerFlow 风格：describe_skill → read_skill_file）=====

SKILL_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "describe_skill",
            "description": "按名称获取已安装技能的描述、参数与输出格式，用于判断该技能是否适合当前任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名（见 <skill_index>）"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "读取技能 SKILL.md 全文，加载其完整工作流/约束/输出要求后严格照做。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名（见 <skill_index>）"},
                },
                "required": ["name"],
            },
        },
    },
]


async def skill_loop(
    state: dict[str, Any],
    sys_prompt: str,
    conv: list[Any],
) -> tuple[str, str, int, int]:
    """Skill 自主发现 ReAct 循环（chat 节点）。

    将 describe_skill / read_skill_file 绑定到 LLM，LLM 按需发现并加载 skill 后直接作答；
    模型不支持 tools 时返回 ("", "", 0, 0)，由调用方降级为普通对话。
    返回 (content, model_id, in_tokens, out_tokens)。
    """
    mc = state.get("model_choice") or {}
    try:
        llm, model_id = await get_llm(mc)
        llm_tools = llm.bind_tools(SKILL_TOOLS)
    except Exception as e:
        log.warning("bind_skill_tools failed: %s", e)
        return "", "", 0, 0

    loop_conv = [
        SystemMessage(content=sys_prompt + "\n\n<skill_system>"
                      "若 <skill_index> 中有与任务匹配的 skill：先调用 describe_skill 查看其能力，"
                      "确认匹配后调用 read_skill_file 加载完整指令并严格按指令执行。"
                      "不需要 skill 时直接回答。</skill_system>"),
        *conv,
    ]
    resp = None
    for _round in range(MAX_TOOL_ROUNDS):
        try:
            resp = await llm_tools.ainvoke(loop_conv)
        except Exception as e:
            log.warning("skill loop round failed: %s", e)
            break
        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            break
        loop_conv.append(AIMessage(content=resp.content or "", tool_calls=tool_calls))
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args") or {}
            tid = tc.get("id", "")
            if name == "describe_skill":
                out = json.dumps(describe_skill(args.get("name", "")), ensure_ascii=False)[:3000]
            elif name == "read_skill_file":
                doc = read_skill_doc(args.get("name", ""))
                out = doc if doc else "（SKILL.md 不存在）"
            else:
                out = "未知工具"
            loop_conv.append(ToolMessage(content=out, tool_call_id=tid))
            log.info("skill discovery tool=%s args=%s", name, args)
    if resp is None:
        return "", "", 0, 0
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    in_t = int(usage.get("input_tokens", 0) or 0)
    out_t = int(usage.get("output_tokens", 0) or 0)
    return content, model_id, in_t, out_t
