# character-development

> triggers: 角色弧光 / 人物发展 / 角色成长 / 人物弧光 / 角色分析 / 人物塑造

## Description

角色弧光建议：为指定角色生成完整的成长弧光（起始状态→关键转折→最终状态），
含每阶段的内在动机、外在行为、关系变化、与主线的呼应。
输出 Markdown 报告，供作者参考细化角色配置（P1-7 角色 page）。

## Parameters

- `book_id` (int)
- `character_name` (str): 角色名（主角/反派/重要配角）
- `character_intro` (str, optional): 角色简介（若已配置）
- `outline` (dict, optional): 整体大纲（用于角色弧光与情节呼应）
- `book_meta` (dict): 书籍元数据
- `arc_stages` (int, default=5): 弧光阶段数（开端/触发/挣扎/转折/新我）

## Workflow

1. backend 加载角色信息 + 大纲 + 书籍元数据
2. 构造 prompt：角色设定 + 大纲关键节点 + 类型惯例 + 弧光阶段数
3. LLM 输出 Markdown 报告：
   - 起始状态（性格/信念/能力/关系）
   - 每阶段：触发事件 / 内在转变 / 外在行为 / 关键对白示例
   - 与主线呼应点
   - 潜在偏离风险（避免崩人设）
4. 返回报告（前端 Markdown 渲染）

## Output

- `report` (str): Markdown 格式角色弧光报告
- `arc_stages` (list[dict]): 结构化阶段（便于前端可视化）
  - `name` (str): 阶段名
  - `internal_state` (str): 内在状态
  - `external_behavior` (str): 外在行为
  - `trigger` (str): 触发事件
- `token_usage` (dict)

## Constraints

- 弧光需有内在逻辑（性格转变不能突兀）
- 与主线情节呼应（转折点对应大纲关键章）
- 对白示例符合角色口吻
- 输出报告语言风格与书籍类型一致
