"""Supervisor 节点：意图识别（多轮上下文感知）。"""
from __future__ import annotations

from storyclaw.agents.state import AgentState


def supervisor(state: AgentState) -> dict:
    """识别 8 类意图（P1-6 扩展）：

    - write:     首次写作（"写本章/续写下一章/撰写"）
    - modify:    修改已生成内容（"把第3段改/再扩写/删掉/改悲伤"）
    - continue:  段内续写（"续写这里/接着这段写/往下写/从光标处续写"）
    - polish:    选中文本润色（"润色选中/打磨这段/优化选中"）
    - analyze:   分析报告（大纲/情节/角色弧光/一致性/前情提要）
    - review:    审校（"检查/审校"）
    - research:  检索（"查找/检索/资料"）
    - assist:    辅助 skill（头脑风暴/标题/场景/对话/阅读配置）
    - chat:      默认对话

    多轮指代识别：当用户说"再扩写/再修改/继续"等指代词时，
    查看历史最近一次 write/modify 意图并继承。
    """
    msgs = state.get("messages") or []
    last = msgs[-1]["content"] if msgs else ""
    has_chapter = bool(state.get("chapter_id") or state.get("current_content"))

    # 明确业务端点的操作优先于用户文本中的关键词，避免“不要修改”被路由为修改。
    preset = state.get("intent")
    if preset in {"write", "modify", "continue", "polish", "assist"}:
        skills = {"write": "write-chapter", "modify": "modify-chapter", "continue": "continue-writing", "polish": "polish-chapter"}
        return {"intent": preset, "active_skill": skills.get(preset, state.get("active_skill")), "status": "running"}

    # 0. 尊重 API 端点预设的 analyze intent（analyze 端点直接设了 intent+active_skill，
    #    其 message 形如 "[skill] 书籍 X" 不含触发关键词，需短路避免误路由到 chat）
    _preset_skill = state.get("active_skill")
    if state.get("intent") == "analyze" and _preset_skill in {
        "outline-planning", "plot-planning", "character-development",
        "consistency-check", "book-summary",
    }:
        return {"intent": "analyze", "active_skill": _preset_skill, "status": "running"}

    # 1. 分析类 skill（优先匹配）
    analyze_rules = [
        ("outline-planning", ["生成大纲", "规划大纲", "整体大纲", "重新规划大纲", "做大纲", "大纲设计"]),
        ("plot-planning", ["规划情节", "情节节点", "设计情节", "情节大纲", "主线支线", "冲突设计"]),
        ("character-development", ["角色弧光", "人物发展", "角色成长", "人物弧光", "角色分析", "人物塑造"]),
        ("consistency-check", ["一致性检查", "一致性报告", "设定检查", "人设检查", "时间线检查", "逻辑检查"]),
        ("book-summary", ["前情提要", "整理前情", "前情回顾", "背景速览"]),
    ]
    for skill, kws in analyze_rules:
        if any(k in last for k in kws):
            return {"intent": "analyze", "active_skill": skill, "status": "running"}

    # 1.5 辅助类 skill
    assist_rules = [
        ("brainstorm", ["头脑风暴", "灵感", "创意", "点子", "想法", "脑洞", "突破瓶颈"]),
        ("title-generation", ["起标题", "章节标题", "取名", "标题生成", "起名"]),
        ("scene-enhance", ["场景增强", "场景描写", "环境描写", "氛围渲染", "场景改写"]),
        ("dialogue-polish", ["对话润色", "对话优化", "台词打磨", "对话改写"]),
        ("reading-config-gen", ["阅读配置", "阅读设置", "阅读模板", "生成阅读配置"]),
    ]
    for skill, kws in assist_rules:
        if any(k in last for k in kws):
            return {"intent": "assist", "active_skill": skill, "status": "running"}

    # 2. 润色（必须先于 modify）
    if state.get("selected_text"):
        return {"intent": "polish", "active_skill": "polish-chapter", "status": "running"}
    polish_keywords = ["润色这段", "润色选中", "优化选中", "打磨这段", "润色一下", "提升文笔"]
    if any(k in last for k in polish_keywords) and has_chapter:
        return {"intent": "polish", "active_skill": "polish-chapter",
                "selected_text": state.get("current_content", "")[:2000],
                "status": "running"}

    # 3. 段内续写（区别于 continue-chapter 的"写下一章"）
    if state.get("prefix_text"):
        return {"intent": "continue", "active_skill": "continue-writing", "status": "running"}
    continue_keywords = ["续写这里", "接着这段写", "往下写", "续写片段", "从光标处续写", "接下去"]
    if any(k in last for k in continue_keywords) and has_chapter:
        return {"intent": "continue", "active_skill": "continue-writing",
                "prefix_text": state.get("current_content", "")[-1500:],
                "status": "running"}

    # 4. 修改类指令（必须先于 write）
    modify_keywords = ["把第", "改成", "改为", "修改", "扩写", "再扩写", "删掉",
                       "删减", "增加", "改悲伤", "改轻松", "改得", "重写第",
                       "调整", "继续写", "再写", "接着写", "继续扩", "再润色"]
    if any(k in last for k in modify_keywords) and has_chapter:
        return {"intent": "modify", "modify_request": last, "status": "running"}

    # 5. 续写下一章
    if any(k in last for k in ["续写下一章", "写下一章", "下一章", "继续写下一"]):
        return {"intent": "write", "status": "running"}

    # 6. 首次写作
    if any(k in last for k in ["写本章", "写第", "生成章节", "续写", "撰写", "写这一章", "批量写", "写多章", "连写"]):
        return {"intent": "write", "status": "running"}

    # 7. 审校
    if any(k in last for k in ["检查", "审校", "审阅", "修改意见", "审稿"]):
        return {"intent": "review", "status": "running"}

    # 8. 检索
    if any(k in last for k in ["检索", "查找", "查一下", "资料"]):
        return {"intent": "research", "status": "running"}

    # 9. 指代性继承
    if any(k in last for k in ["再", "继续", "还是", "接着"]) and has_chapter:
        for m in reversed(msgs[:-1]):
            if m.get("role") == "assistant" and len(m.get("content", "")) > 100:
                return {"intent": "modify", "modify_request": last, "status": "running"}

    return {"intent": "chat", "status": "running"}
