# title-generation

> triggers: 起标题 / 章节标题 / 取名 / 标题生成 / 起名 / 标题

## Description

标题生成：根据章节内容/关键词/风格偏好，生成多个候选标题。
用于章节定稿前的标题选择、卷名命名、书名候选。

## Parameters

- `content` (str, optional): 章节正文或摘要（用于提取主题）
- `keywords` (list[str], optional): 关键词列表
- `style` (str, default="classic"): classic | poetic | suspense | light
  - classic: 经典四字/对仗（如"剑破苍穹"）
  - poetic: 诗意抒情（如"月下花前"）
  - suspense: 悬疑钩子（如"谁在暗处"）
  - light: 轻松网文风（如"我被困在同一天"）
- `count` (int, default=6): 候选数量
- `target` (str, optional): "chapter" | "volume" | "book"，命名对象
- `model_choice` (dict)

## Workflow

1. 提取章节核心事件/情感/意象（若有 content）
2. 构造 prompt：内容摘要 + 风格 + 数量 + 命名对象约束
3. LLM 生成：每条标题含「标题 + 适配理由」
4. 返回编号列表

## Output

- `titles` (str): Markdown 编号列表，每条含标题+理由
- `token_usage` (dict)

## Constraints

- 标题字数：章节 4-8 字，卷名 2-6 字，书名 2-10 字
- 不与已有章节标题重复（注入 context 时）
- 覆盖多种风格变体，避免同质化
- 契合内容核心，不剧透关键反转
