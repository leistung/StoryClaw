from .skills import method_instructions
"""Structured creative dossiers; model outputs are proposals, never implicit DB writes."""
import json
from typing import Literal
from pydantic import BaseModel,Field
from ._util import llm_respond,strip_code_fence

class Dossier(BaseModel):
    name:str=Field(min_length=1,max_length=128)
    category:str=Field(min_length=1,max_length=50)
    description:str=Field(min_length=20,max_length=3000)
    extra:dict=Field(default_factory=dict)
class DesignDraft(BaseModel):
    summary:str=Field(min_length=1,max_length=1000)
    dossiers:list[Dossier]=Field(min_length=1,max_length=12)

async def generate_design(kind:Literal['character','world','plot'],book:dict,outline:dict,existing:list[dict],model_choice:dict):
    goals={
      'character':'设计核心角色卡，覆盖身份、欲望、恐惧、底线、关系和成长弧。不得改变已有角色性格/身份；后续设定不能冒充已发生事实。',
      'world':'设计适合题材的世界观规则卡：时代地理、社会制度、资源/能力限制、禁忌、叙事边界。现实题材不得硬套修炼体系。',
      'plot':'设计主线、支线与伏笔规划，写明埋设、推进、回收的计划章号；明确这是未来规划，不是已发生正文。'}
    system=('你是原创小说策划。'+goals[kind]+'参考已确认大纲、开书卡和作者现有设定，不覆盖原有资料；只提供少量有用草案，不预先制造无关档案。'
       '只输出JSON：{"summary":"设计说明与待确认处","dossiers":[{"name":"档案名","category":"分类","description":"完整描述","extra":{"可选补充字段":"内容"}}]}。1到12张卡。资料若标注省略了节点，不能声称已经审阅所有章节，也不能擅自推翻已有设定。')
    # Bound whole records, never cut serialized JSON (which can discard author canon).
    nodes=[c for v in outline.get('volumes',[]) for c in v.get('chapters',[])]
    selected={id(c) for c in (nodes if len(nodes)<=80 else nodes[:40]+nodes[-40:])}
    outline_brief={'overview':str(outline.get('overview',''))[:3000],'omitted_chapters':max(0,len(nodes)-80),'volumes':[
        {'name':str(v.get('name',''))[:200],'goal':str(v.get('goal',''))[:400],'chapters':[{**c,'summary':str(c.get('summary',''))[:250]} for c in v.get('chapters',[]) if id(c) in selected]} for v in outline.get('volumes',[])[:80]]}
    payload={'book':{k:v[:3000] if isinstance(v,str) else v for k,v in book.items()},'existing':[{**r,'description':str(r.get('description',''))[:500]} for r in existing[:40]],'omitted_settings':max(0,len(existing)-40),'outline':outline_brief}
    text,ins,outs,model=await llm_respond({'model_choice':model_choice,'response_format':{'type':'json_object'}},system+'\n'+method_instructions({'world':'world-design','character':'character-arc','plot':'plot-design'}[kind]),json.dumps(payload,ensure_ascii=False))
    result=DesignDraft.model_validate(json.loads(strip_code_fence(text)))
    return result,ins,outs,model
