from storyclaw.skills.loader import method_instructions
"""Structured creative dossiers; model outputs are proposals, never implicit DB writes."""
import json
from typing import Literal
from pydantic import BaseModel,Field
from storyclaw.models.calls import llm_respond
from storyclaw.models.calls import strip_code_fence

class Dossier(BaseModel):
    name:str=Field(min_length=1,max_length=128)
    category:str=Field(min_length=1,max_length=50)
    description:str=Field(min_length=20,max_length=3000)
    extra:dict=Field(default_factory=dict)
class DesignDraft(BaseModel):
    summary:str=Field(min_length=1,max_length=1000)
    dossiers:list[Dossier]=Field(min_length=1,max_length=36)

async def generate_design(kind:Literal['character','world','plot'],book:dict,outline:dict,existing:list[dict],model_choice:dict,creation_plan=None):
    goals={
      'character':'设计核心角色卡，覆盖身份、欲望、恐惧、底线、关系和成长弧。不得改变已有角色性格/身份；后续设定不能冒充已发生事实。',
      'world':'设计适合题材的世界观规则卡：时代地理、社会制度、资源/能力限制、禁忌、叙事边界。现实题材不得硬套修炼体系。',
      'plot':'设计主线、支线与伏笔规划，写明埋设、推进、回收的计划章号；明确这是未来规划，不是已发生正文。'}
    system=('你是原创小说策划。'+goals[kind]+'参考已确认大纲、开书卡和作者现有设定，不覆盖原有资料；按确认计划充分展开具体档案，避免空泛标签和无关档案。'
       '只输出JSON：{"summary":"设计说明与待确认处","dossiers":[{"name":"档案名","category":"分类","description":"完整描述","extra":{"可选补充字段":"内容"}}]}。1到12张卡。资料若标注省略了节点，不能声称已经审阅所有章节，也不能擅自推翻已有设定。')
    # Bound whole records, never cut serialized JSON (which can discard author canon).
    nodes=[c for v in outline.get('volumes',[]) for c in v.get('chapters',[])]
    selected={id(c) for c in (nodes if len(nodes)<=80 else nodes[:40]+nodes[-40:])}
    outline_brief={'overview':str(outline.get('overview',''))[:3000],'omitted_chapters':max(0,len(nodes)-80),'volumes':[
        {'name':str(v.get('name',''))[:200],'goal':str(v.get('goal',''))[:400],'chapters':[{**c,'summary':str(c.get('summary',''))[:250]} for c in v.get('chapters',[]) if id(c) in selected]} for v in outline.get('volumes',[])[:80]]}
    payload={'book':{k:v[:3000] if isinstance(v,str) else v for k,v in book.items()},'existing':[{**r,'description':str(r.get('description',''))[:500]} for r in existing[:40]],'omitted_settings':max(0,len(existing)-40),'outline':outline_brief}
    from storyclaw.workflows.creation_plan import CreationPlan
    from storyclaw.runtime.progress import progress
    plan=CreationPlan.model_validate(creation_plan) if creation_plan else None
    count=plan.item_count if plan else 12;words=plan.detail_words if plan else 450
    payload['creation_plan']=plan.model_dump() if plan else None
    cards=[];ins=outs=0;summary='';names={r['name'] for r in existing if r.get('entity_type')==kind}
    for first in range(0,count,3):
        batch_count=min(3,count-first)
        await progress('step.started','design.batch',label=f'生成第{first+1}–{first+batch_count}/{count}张档案',design_type=kind)
        instruction=f'本批恰好新增{batch_count}张卡，每张description目标{words}字，至少{max(120,int(words*.6))}字。按计划分组覆盖不同职责，写明具体行为、关系、冲突和变化；不与existing或generated同名。'
        text,ti,to,model=await llm_respond({'model_choice':model_choice,'response_format':{'type':'json_object'},'response_max_tokens':8192},system+'\n'+instruction+'\n'+method_instructions({'world':'world-design','character':'character-arc','plot':'plot-design'}[kind]),json.dumps({**payload,'generated':[c.model_dump() for c in cards]},ensure_ascii=False))
        result=DesignDraft.model_validate(json.loads(strip_code_fence(text)))
        if len(result.dossiers)!=batch_count:raise ValueError('档案数量未达到计划，本次未采用；请核对用量后调整计划')
        for card in result.dossiers:
            if card.name in names or len(card.description.strip())<max(120,int(words*.6)):raise ValueError('档案重复或展开不足，本次未采用')
            names.add(card.name)
        cards.extend(result.dossiers);ins+=ti;outs+=to;summary=result.summary
        await progress('step.completed','design.batch',label=f'已生成{len(cards)}/{count}张档案',names=[c.name for c in result.dossiers])
    return DesignDraft(summary=summary,dossiers=cards),ins,outs,model
