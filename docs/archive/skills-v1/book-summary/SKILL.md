# book-summary

> triggers: 前情提要 / 整理前情 / 内容摘要 / 章节摘要 / 前情回顾 / 背景速览

## Description

前情提要：给定章节范围，生成结构化摘要（主线推进/关键人物/重要事件/伏笔状态）。
用于续写时注入 prev_chapter_summary、用户回归创作时的快速回顾、
阅读页的"前情提要"展示。

## Parameters

- `book_id` (int)
- `chapter_range` (dict): {"start": 1, "end": 10}
- `summary_style` (str, default="structured"): structured | narrative
  - structured: 分块（主线/人物/事件/伏笔）
  - narrative: 连续叙述（500 字内）
- `max_length` (int, default=800): narrative 模式最大字数
- `model_choice` (dict)

## Workflow

1. backend 加载范围内章节内容
2. 可选注入 RAG 实体关系（人物/场景/物品）
3. 构造 prompt：章节文本 + 摘要风格 + 长度限制
4. LLM 输出：
   - structured: {"main_line":"...", "characters":[{"name":"","state":""}], "events":[...], "foreshadowing":[...]}
   - narrative: 一段连续叙述
5. 返回摘要 + 写回缓存（可选）

## Output

- `summary` (dict|str): structured 模式返回 dict，narrative 返回 str
- `chapter_range` (dict): 实际覆盖范围
- `token_usage` (dict)

## Constraints

- structured 模式：主线每章必须有推进，人物只列有变化的
- narrative 模式：自然过渡，不堆砌事件清单
- 不剧透未发生的伏笔回收
- 字数严格限制
