# polish-chapter

> triggers: 润色这段 / 润色选中 / 优化选中 / 打磨这段 / 润色一下 / 提升文笔

## Description

选中文本润色：对编辑器中用户选中的一段文字进行文笔润色，
提升表达力、节奏感、画面感，但严格保留原意、人物、情节、信息量。
与 modify-chapter（重写整章）不同，本 skill 只处理选中的片段，输出润色版片段。

## Parameters

- `chapter_id` (int): 当前章节（用于加载元数据/人物设定）
- `selected_text` (str): 用户选中的待润色文本（500-2000 字为宜）
- `polish_goal` (str, optional): 润色方向（如"更悲情""更紧凑""更有画面感""对白更自然"）
- `chapter_meta` (dict): 章节元数据
- `user_memory` (dict): 用户长期偏好（tone/pov）

## Workflow

1. backend 接收 selected_text + polish_goal
2. 构造 prompt：原文 + 润色方向 + 用户文风偏好
3. LLM 输出润色版片段（长度与原文相近，±20%）
4. 片段返回前端，替换选区（由前端决定是否接受）
5. 不直接写回 Chapter.content（用户点"接受"后才入库）

## Output

- `content` (str): 润色后的片段
- `word_count` (int): 润色版字数
- `token_usage` (dict)

## Constraints

- 严格保留原意，不增删情节信息
- 人物名字、称谓、视角保持一致
- 长度与原文 ±20%
- 只输出润色版片段，不带前言/解释
- 文风与用户长期偏好一致
