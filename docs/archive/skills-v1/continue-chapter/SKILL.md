# continue-chapter

> triggers: 续写下一章 / 写下一章 / 下一章 / 继续写下一

## Description

基于已生成章节的内容摘要，生成下一章正文。
Supervisor 识别"续写下一章"后，backend 自动定位下一章 ID（number+1），
将该章大纲节点 + 当前章节内容作为 prev_chapter_summary 注入 Writer。
实际复用 write-chapter skill 的 _writer_write 模式，区别仅在上下文加载。

## Parameters

- `book_id` (int)
- `current_chapter_id` (int): 当前所在章节 ID（用于定位下一章）
- `next_chapter_id` (int): 自动解析的下一章 ID
- `chapter_meta` (dict): 下一章元数据
- `outline_node` (dict): 下一章的大纲节点
- `prev_chapter_summary` (str): 当前章节内容摘要（后端截断前 600 字）

## Workflow

1. 用户在 Ask 面板输入"续写下一章"
2. backend _build_input 检测关键词 → 调 _find_next_chapter 解析 next_chapter_id
3. build_write_context 加载下一章的 chapter_meta + outline_node + prev_summary（取自当前章节）
4. Supervisor intent=write → Writer _writer_write 模式
5. Reviewer 字数自检
6. 写回下一章 Chapter.content

## Output

- `content` (str): 下一章正文
- `word_count` (int)
- `token_usage` (dict)

## Constraints

- 续写需承接前章情节，避免信息重复
- 紧扣下一章大纲节点
- 直接输出章节正文
