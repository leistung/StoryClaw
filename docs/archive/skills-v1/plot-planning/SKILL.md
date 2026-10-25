# plot-planning

> triggers: 规划情节 / 情节节点 / 设计情节 / 情节大纲 / 主线支线 / 冲突设计

## Description

情节节点规划：基于整体大纲，为每章细化情节节点（开端/发展/转折/高潮/收束），
识别主线与支线、伏笔与回收、冲突点。输出结构化情节节点 JSON，
供后续写作时注入 Writer 上下文，让章节生成更紧扣节奏。

## Parameters

- `book_id` (int)
- `outline` (dict): 整体大纲（volumes → chapters）
- `book_meta` (dict): 书籍元数据（类型/主角/字数目标）
- `focus_chapters` (list[int], optional): 只规划指定章号，缺省为全部

## Workflow

1. backend 加载大纲 + 书籍元数据
2. 构造 prompt：大纲 + 主角设定 + 类型惯例 + 用户偏好
3. LLM 输出每章情节节点 JSON：
   ```json
   {"chapters":[{"number":1,"beats":[{"name":"开端","content":"..."},{"name":"伏笔","content":"..."}],"main_line":"...","sub_lines":[...]}]}
   ```
4. 返回结构化结果（前端在大纲/情节页展示）
5. 可选写回 Plot 表（P1-7 配置页面落地）

## Output

- `chapters` (list[dict]):
  - `number` (int)
  - `beats` (list[dict]): 情节节点
    - `name` (str): 开端/发展/转折/高潮/收束/伏笔/回收
    - `content` (str): 节点描述（30-80 字）
  - `main_line` (str): 该章主线推进
  - `sub_lines` (list[str]): 支线推进
- `foreshadowing` (list[dict]): 伏笔清单
  - `id` (str)
  - `planted_at` (int): 埋伏章号
  - `resolved_at` (int|null): 回收章号
  - `description` (str)

## Constraints

- 节奏张弛有度，避免一章内堆砌过多转折
- 主线每章必须有推进（不能原地踏步）
- 伏笔需有回收规划
- 只输出 JSON，不带前言
