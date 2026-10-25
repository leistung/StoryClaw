# dialogue-polish

> triggers: 对话润色 / 对话优化 / 台词打磨 / 对话改写 / 角色对话

## Description

对话润色：对给定对话文本进行个性化与戏剧性优化，让每个角色的语言风格鲜明。
用于对话平淡时的性格强化、信息密度提升、潜台词与冲突感增强。

## Parameters

- `dialogue_text` (str): 待润色的对话文本
- `characters` (list[dict], optional): 角色信息 [{"name":"","personality":"","speech_style":""}]
- `goal` (str, default="personalize"): personalize | conflict | info_dense | subtext
  - personalize: 强化角色语言风格区分度
  - conflict: 增强对话冲突与张力
  - info_dense: 提升信息密度（每句推进情节）
  - subtext: 增加潜台词与言外之意
- `preserve_info` (bool, default=true): 是否保留原文关键信息点
- `model_choice` (dict)

## Workflow

1. 分析原对话的角色发言分布与信息点
2. 注入角色性格档案（若有）
3. 构造 prompt：原文 + 角色 + 目标 + 约束
4. LLM 生成润色后对话
5. 返回完整对话段落

## Output

- `polished_dialogue` (str): 润色后的对话文本
- `token_usage` (dict)

## Constraints

- 不改变对话传递的关键信息
- 每个角色语言风格需有辨识度（用词/句式/口头禅）
- 对话推进节奏，删除无意义寒暄
- 潜台词通过行为/表情暗示，不直白说出
- 保留原文中的人物关系设定
