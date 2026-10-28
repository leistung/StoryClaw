"""Reviewable scope for expensive planning and dossier generation."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from storyclaw.models.calls import llm_respond, strip_code_fence
from storyclaw.skills.loader import method_instructions

class PlanSection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    brief: str = Field(min_length=20, max_length=1200)

class CreationPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goal: str = Field(min_length=20, max_length=2000)
    sections: list[PlanSection] = Field(min_length=1, max_length=12)
    item_count: int = Field(ge=1, le=36)
    detail_words: int = Field(ge=200, le=1200)
    notes: str = Field(default='', max_length=2000)

async def propose_plan(kind: Literal['outline','character','world','plot'], context: dict):
    system = '''你是小说创作统筹。先拟可讨论的执行计划，不生成正式大纲或档案。
根据作品题材、预计篇幅、已有设定和作者补充安排规模，不机械追求少量，也不要堆无关人物。
大纲：sections 是建议的卷，每卷 brief 说明主冲突、重要事件、角色变化与收束点，通常3到8卷；item_count等于卷数，detail_words是每卷正式展开的目标字数，建议500到900字。
角色：sections是角色组（主角、对手、盟友等），brief提出具体人物及关系；item_count是新增角色总数，通常8到18个；detail_words是每张卡目标字数，建议300到600字。
世界观/情节：sections是规则或主支线分组，说明具体内容；item_count是新增档案总数，通常8到16张，每张300到600字。已有同名档案不重复创建。
尊重作者明确要求。连载卷只是可调整的阶段，不预先锁死结局和全部章纲。
只输出JSON：{"goal":"结合本书的创作目标","sections":[{"name":"卷名或分组","brief":"具体内容"}],"item_count":12,"detail_words":500,"notes":"需要作者核对的假设和建议补充的问题"}。'''
    method = {'outline':'framework-design', 'character':'character-arc',
              'world':'world-design', 'plot':'plot-design'}[kind]
    # 计划阶段也使用对应方法；只影响本次提示，不增加模型调用或绕过确认。
    text, *_ = await llm_respond({'model_choice':{'kind':'business'}, 'response_max_tokens':4096,
                                  'response_format':{'type':'json_object'}}, system+'\n'+method_instructions(method),
                                 json.dumps({'kind':kind, **context},ensure_ascii=False))
    plan = CreationPlan.model_validate(json.loads(strip_code_fence(text)))
    if kind == 'outline': plan.item_count = len(plan.sections)
    return plan
