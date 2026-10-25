# continue-writing

> triggers: 续写这里 / 接着这段写 / 往下写 / 续写片段 / 从光标处续写 / 接下去

## Description

段内续写：基于光标位置前的章节内容，续写一段（300-800 字）片段。
与 continue-chapter（写完整下一章）不同，本 skill 用于在当前章节内追加内容，
适用于作者卡文时让 AI 接着已有文字往下写一小段，再人工取舍。

## Parameters

- `chapter_id` (int): 当前章节
- `prefix_text` (str): 光标前的章节内容（截断到最近 1500 字）
- `cursor_position` (int, optional): 光标字符偏移
- `max_words` (int, default=600): 续写片段目标字数
- `chapter_meta` (dict): 章节元数据（标题/序号/目标字数）
- `outline_node` (dict): 当前章节大纲节点（提供情节方向）
- `user_memory` (dict): 用户长期偏好

## Workflow

1. backend 截取光标前 1500 字作为 prefix
2. 注入 prefix + outline_node + 用户偏好构造 prompt
3. LLM 生成续写片段（不重写已有内容，只输出新片段）
4. 片段返回前端，光标位置插入（由前端决定是否接受）
5. 不直接写回 Chapter.content（由用户点"接受"后才入库）

## Output

- `content` (str): 续写片段正文
- `word_count` (int): 片段字数
- `token_usage` (dict)

## Constraints

- 只输出新片段，不重复 prefix 内容
- 风格、人物、视角与 prefix 保持一致
- 不带前言/解释/Markdown 标题
- 片段长度控制在 max_words 附近
