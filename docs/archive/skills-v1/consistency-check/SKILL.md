# consistency-check

> triggers: 一致性检查 / 一致性报告 / 设定检查 / 人设检查 / 时间线检查 / 逻辑检查

## Description

一致性报告：扫描指定章节范围，检查人设/时间线/世界观/伏笔回收/称谓一致性，
输出问题清单 + 修复建议。基于 RAG 检索（实体关系图 + 向量切片）+ LLM 推理。
适用于作者在多章生成后做整体审校，避免崩人设、设定冲突、伏笔遗漏。

## Parameters

- `book_id` (int)
- `chapter_range` (dict): {"start": 1, "end": 10} 检查范围
- `check_dimensions` (list[str], optional): 默认 ["character","timeline","worldbuilding","foreshadowing","naming"]
- `outline` (dict, optional): 大纲（对照实际是否偏离）
- `rag_context` (dict, optional): RAG 检索的实体关系（P0-5 数据库页）
- `model_choice` (dict)

## Workflow

1. backend 加载范围内章节内容 + 大纲 + RAG 实体关系
2. 对每个 dimension 构造检查 prompt：
   - character: 角色名字/称谓/能力/性格是否前后矛盾
   - timeline: 事件时间顺序是否合理（"昨日"与"三日前"对不上）
   - worldbuilding: 设定规则是否被违反（如修为体系/魔法体系）
   - foreshadowing: 大纲伏笔是否被回收
   - naming: 同一实体是否多种称呼（"林深"vs"林公子"未说明）
3. LLM 输出每个 dimension 的问题清单 JSON
4. 汇总报告：问题数 / 严重程度 / 修复建议
5. 返回 Markdown 报告 + 结构化 issues

## Output

- `report` (str): Markdown 一致性报告
- `issues` (list[dict]):
  - `dimension` (str): character|timeline|worldbuilding|foreshadowing|naming
  - `severity` (str): high|medium|low
  - `chapter` (int): 出问题的章号
  - `description` (str): 问题描述
  - `suggestion` (str): 修复建议
- `summary` (dict): {"total": N, "high": N, "medium": N, "low": N}
- `token_usage` (dict)

## Constraints

- 基于 RAG 检索 + 章节文本，不凭空臆测
- 问题需有具体章节引用（"第5章称林公子，第7章突然变林深且未交代关系变化"）
- 修复建议可操作（"建议在第7章加一句她改口直呼其名以示亲近"）
- 无问题时输出 ✓ 一致性检查通过
