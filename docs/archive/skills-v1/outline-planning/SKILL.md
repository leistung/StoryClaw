# outline-planning

> triggers: 生成大纲 / 规划大纲 / 整体大纲 / 重新规划大纲 / 做大纲 / 大纲设计

## Description

整体大纲规划：基于书籍元数据（书名/类型/简介/主角/预计章数/字数），
生成完整的卷章结构 + 每章梗概。输出严格 JSON，写入 Outline 表。
backend 已有 /api/outlines 端点（P1-1），本 skill 为其 Agent 入口。

## Parameters

- `book_id` (int)
- `book_meta` (dict):
  - `title` (str)
  - `genre` (str)
  - `intro` (str)
  - `protagonist_name` (str)
  - `protagonist_intro` (str)
  - `target_chapters` (int)
  - `target_words` (int)
  - `per_chapter_words` (int)

## Workflow

1. backend 加载 book_meta
2. 调用 outline_graph（StateGraph）的 plan_outline 节点
3. plan_outline 尝试 LLM 生成 JSON 大纲，失败则降级为模板大纲
4. 写回 Outline.content（覆盖旧大纲，需用户确认）
5. 返回大纲预览

## Output

- `outline` (dict):
  - `volumes` (list[dict]):
    - `name` (str)
    - `chapters` (list[dict]):
      - `number` (int)
      - `title` (str)
      - `summary` (str): 50 字内梗概
- `error` (str|null): LLM 不可用时记录降级原因

## Constraints

- 章节总数必须等于 target_chapters
- 合理分卷（每 5-10 章一卷）
- 标题贴合类型与主角设定
- 只输出 JSON，不带前言/解释
