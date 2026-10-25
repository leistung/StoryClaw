# modify-chapter

> triggers: 修改 / 扩写 / 删减 / 把第N段改 / 再扩写 / 润色这段 / 优化这段 / 重写第 / 调整

## Description

基于当前章节内容和用户修改要求，重写整章正文。
用于多轮迭代：用户生成章节后，提出具体修改意见，Agent 走 modify 模式重写。
Reviewer 节点会用 LLM 检查修改要求是否满足，不满足则回到 Writer 重试（最多 1 次）。

## Parameters

- `chapter_id` (int): 要修改的章节 ID
- `current_content` (str): 当前章节完整内容
- `modify_request` (str): 用户的修改要求（如"把第3段改悲伤""扩写到4000字""删掉配角李四"）
- `chapter_meta` (dict): 章节元数据
  - `title` (str)
  - `number` (int)
  - `per_chapter_words` (int)
- `user_memory` (dict): 用户长期写作偏好

## Workflow

1. Supervisor 识别 modify 关键词 + 有 current_content → intent=modify
2. Writer 走 _writer_modify 模式：构造 MODIFY_SYSTEM prompt（注入 current_content + modify_request）
3. Reviewer 用 LLM 判断 draft 是否满足 modify_request
   - 不满足 + round < 2 → 回到 Writer 重写
   - 满足或 round >= 2 → 通过
4. 写回 Chapter.content + 更新 word_count

## Output

- `content` (str): 修改后的完整章节正文
- `word_count` (int)
- `token_usage` (dict)
- `review_feedback` (str): 包含 LLM 判断的修改满足度说明

## Constraints

- 严格遵循用户修改要求，保留未涉及部分的原有内容
- 直接输出完整章节正文，不附带前言/解释
- 文风与用户长期偏好一致
