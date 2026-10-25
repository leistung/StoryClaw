"""Agent 状态定义：OutlineState（大纲规划子图）+ AgentState（主 Agent Loop）。"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class OutlineState(TypedDict):
    book_meta: dict[str, Any]
    outline: dict[str, Any] | None
    error: str | None


class AgentState(TypedDict, total=False):
    user_id: int
    book_id: int | None
    chapter_id: int | None
    thread_id: str
    # 多轮消息，resume 时追加
    messages: Annotated[list[dict[str, str]], operator.add]
    intent: str                              # write | modify | continue | polish | analyze | research | review | chat | assist
    active_skill: str | None                 # write-chapter 等
    context: dict                            # outline / prev_chapter_summary / chapter_meta
    draft_content: str
    review_feedback: str
    review_round: int
    token_usage: dict                        # {"in_tokens":0,"out_tokens":0,"model_id":""}
    model_choice: dict                       # {"kind":"local"|"business", ...}
    user_memory: dict                        # 长期写作偏好
    modify_request: str
    current_content: str
    status: str                              # running | finished | error | review_retry
    error: str | None
    error_code: str | None
    # P1-6 扩展
    selected_text: str
    polish_goal: str
    prefix_text: str
    chapter_range: dict
    analysis_report: str
    # P1-8 辅助
    scene_text: str
    dialogue_text: str
