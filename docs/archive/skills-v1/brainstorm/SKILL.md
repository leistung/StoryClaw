# brainstorm

> triggers: 头脑风暴 / 灵感 / 创意 / 点子 / 想法 / 脑洞 / 突破瓶颈

## Description

头脑风暴：根据给定主题/类型/方向，生成多条创意建议（情节转折、角色冲突、世界观设定、伏笔设计等）。
用于卡文时突破瓶颈、新书立项时的设定发散、支线拓展。

## Parameters

- `topic` (str): 头脑风暴主题，如"主角身世反转""新支线""世界设定"
- `genre` (str, optional): 作品类型，如"玄幻""都市""言情"
- `direction` (str, optional): 期望方向，如"黑暗向""轻松向""悬疑"
- `count` (int, default=8): 期望创意条数
- `context` (dict, optional): 书籍元信息（书名/主角/已有大纲）
- `model_choice` (dict)

## Workflow

1. 注入书籍元信息（书名/类型/主角/大纲节点）
2. 构造 prompt：主题 + 类型 + 方向 + 创意条数 + 发散维度要求
3. LLM 生成：每条创意含「标题 + 一句话描述 + 可行性评估」
4. 返回 Markdown 列表

## Output

- `suggestions` (str): Markdown 格式创意列表，每条含标题/描述/可行性
- `token_usage` (dict)

## Constraints

- 创意需与现有设定不冲突（注入 context 时）
- 每条创意独立可执行，不依赖其他创意
- 覆盖多个维度（情节/角色/设定/伏笔），不重复角度
- 标题简短（10字内），描述清晰（30字内）
