# write-chapter

> triggers: 写本章 / 写第N章 / 续写 / 生成章节 / 撰写

## Description

根据书籍大纲、当前章节元数据和前章摘要，撰写当前章节正文。
是 StoryClaw 写作流的核心 skill，由 Writer 子图节点调用。

无 RAG 版本（P0-4）：仅依赖注入的 outline_node + prev_chapter_summary + chapter_meta。
P0-5 将接入 Milvus/Neo4j 检索，补充人物设定、世界观、伏笔等上下文。

## Parameters

- `chapter_id` (int): 当前章节 ID
- `chapter_meta` (dict):
  - `title` (str): 章节标题
  - `number` (int): 章节序号
  - `per_chapter_words` (int): 目标字数
- `outline_node` (dict): 当前章节对应的大纲节点
  - `number` (int)
  - `title` (str)
  - `summary` (str): 大纲梗概
- `prev_chapter_summary` (str): 前一章摘要（首章为空字符串）
- `user_memory` (dict): 用户长期写作偏好
  - `tone` (str): 文风偏好
  - `pov` (str): 视角
  - `custom` (dict): 其他自定义偏好

## Workflow

1. Writer 节点读取上述参数构造 system prompt
2. 调用注入的 LLM 生成正文
3. Reviewer 节点做字数自检
   - 字数 < 目标 x 80% 且重试轮次 < 2 回到 Writer 扩写
   - 否则通过，写入 draft_content

## Output

- `content` (str): 章节正文
- `word_count` (int): 字数统计
- `token_usage` (dict):
  - `in_tokens` (int)
  - `out_tokens` (int)
  - `model_id` (str)

## Constraints

- 直接输出章节正文，不附带前言/解释/Markdown 标题
- 严禁出现"好的，以下是..."之类元话语
- 文风需与用户长期偏好（user_memory.tone）一致
