# write-multi-chapters

> triggers: 批量写 / 写多章 / 连写 / 从第N章写到第M章 / 一次写N章 / 连续生成

## Description

批量生成多章正文。给定起止章号或章数，循环调用 write-chapter 逻辑逐章生成，
每章生成后自动写回 Chapter.content 并更新字数，断点续写（已生成的章节跳过）。
适用于作者希望一次性产出多章草稿、再逐章精修的场景。

## Parameters

- `book_id` (int)
- `start_number` (int): 起始章号（含）
- `end_number` (int): 结束章号（含），与 `count` 二选一
- `count` (int): 连写章数（从 start_number 起算），与 `end_number` 二选一
- `skip_existing` (bool, default=true): 已有内容的章节是否跳过
- `model_choice` (dict): LLM 选择
- `user_memory` (dict): 用户长期偏好

## Workflow

1. backend 解析起止范围，加载书籍 + 大纲
2. 对范围内每一章：
   a. 若 skip_existing 且 Chapter.content 已存在 → 跳过
   b. 加载该章 outline_node + prev_chapter_summary（取自上一章生成结果）
   c. 调用 _writer_write 生成正文
   d. 写回 Chapter.content + 更新 word_count
   e. 累计 token_usage
3. 全部完成后返回每章 {chapter_id, number, title, word_count, status}
4. 任意一章失败 → 记录错误，继续下一章（不阻塞批量）

## Output

- `chapters` (list[dict]): 每章生成结果
  - `chapter_id` (int)
  - `number` (int)
  - `title` (str)
  - `word_count` (int)
  - `status` (str): generated | skipped | error
  - `error` (str|null)
- `total_tokens` (dict): 累计 {in_tokens, out_tokens, model_id}

## Constraints

- 每章独立生成，章间通过 prev_chapter_summary 衔接
- 不并行（保证情节连续性）
- 单章失败不阻塞后续
- 每章生成后立即写回 DB（断点续写基础）
