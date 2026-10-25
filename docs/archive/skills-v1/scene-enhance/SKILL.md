# scene-enhance

> triggers: 场景增强 / 场景描写 / 环境描写 / 氛围渲染 / 场景改写

## Description

场景增强：对给定场景文本进行感官扩充与氛围渲染，增加画面感与沉浸感。
用于平淡场景的文笔提升、关键场景的氛围强化、转场描写的润色。

## Parameters

- `scene_text` (str): 待增强的场景文本
- `senses` (list[str], optional): 期望强化的感官维度，如 ["视觉","听觉","嗅觉","触觉"]
- `mood` (str, optional): 期望氛围，如"紧张""温馨""压抑""苍凉"
- `pov` (str, optional): 视角，如"第一人称""第三人称限知"
- `preserve_length` (bool, default=false): 是否保持原长度（true=替换式润色，false=扩写）
- `model_choice` (dict)

## Workflow

1. 分析原场景文本的叙事要素（时间/地点/人物/动作）
2. 构造 prompt：原文 + 感官维度 + 氛围 + 视角 + 长度约束
3. LLM 生成增强后文本
4. 返回完整场景段落

## Output

- `enhanced_scene` (str): 增强后的场景文本（HTML 或纯文本）
- `token_usage` (dict)

## Constraints

- 不改变原有情节走向与人物动作
- 感官描写自然融入叙事，不堆砌形容词
- 氛围与情绪基调一致
- 扩写模式增量不超过原文 2 倍
- 保留原文关键信息点（人物名/地点/时间）
