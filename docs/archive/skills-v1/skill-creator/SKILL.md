# skill-creator

> triggers: 创建skill / 新建skill / 自定义skill / skill创建 / 生成技能

## Description

Skill 创建器：根据用户描述自动生成 SKILL.md 元数据文件和参考文档。
用于扩展 StoryClaw 的能力边界，让用户自定义创作辅助流程。

## Parameters

- `skill_name` (str): skill 名称（英文 kebab-case，如 my-custom-skill）
- `description` (str): skill 用途描述
- `triggers` (list[str], optional): 触发关键词列表
- `parameters` (list[dict], optional): 参数定义 [{"name":"","type":"","desc":"","default":""}]
- `output_format` (str, optional): 期望输出格式描述
- `model_choice` (dict)

## Workflow

1. 根据描述生成 SKILL.md（triggers/Description/Parameters/Workflow/Output/Constraints）
2. 生成 references/ 参考文档（如需）
3. 返回创建结果和文件路径

## Output

- `skill_md` (str): 生成的 SKILL.md 内容
- `skill_path` (str): 文件路径
- `token_usage` (dict)

## Constraints

- skill_name 必须是 kebab-case（小写+连字符）
- triggers 至少 3 个关键词
- Parameters 必须包含 model_choice
- 生成的 SKILL.md 需符合现有格式规范
