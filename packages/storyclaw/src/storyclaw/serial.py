from .skills import method_instructions
"""Rolling novel planning: stable framework, confirmed next-chapter blueprint."""
import hashlib
import json
from pydantic import BaseModel,Field
from ._util import llm_respond,strip_code_fence

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

def framework_content(content):
    if content.get('planning_mode')!='serial':return {k:v for k,v in content.items() if k!='_review'}
    return {'planning_mode':'serial','overview':content.get('overview',''),'volumes':[{'name':v.get('name',''),'goal':v.get('goal','')} for v in content.get('volumes',[])]}

class Stage(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    goal:str=Field(min_length=10,max_length=2000)
class Framework(BaseModel):
    overview:str=Field(min_length=20,max_length=6000)
    volumes:list[Stage]=Field(min_length=1,max_length=6)
class Blueprint(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    summary:str=Field(min_length=20,max_length=3000)
    ending_hook:str=Field(default='',max_length=1000)
    constraints:list[str]=Field(default_factory=list,max_length=12)

async def generate_framework(meta):
    prompt=('你是原创连载小说总策划。只确定故事总方向和近期1到3个阶段目标，不锁定总章数，不预写所有章纲，不因为目标字数就提前完结。'
      '总纲包含核心冲突、主角目标、规则边界、长期悬念与可调整的收束方向。章节数与字数仅是暂定规模。'
      '只输出JSON：{"overview":"总纲","volumes":[{"name":"阶段或卷名","goal":"阶段目标、主要变化与可调整边界"}]}。不要输出chapters。')
    raw,*_=await llm_respond({'model_choice':{'kind':'business'},'response_format':{'type':'json_object'}},prompt+'\n'+method_instructions('framework-design'),json.dumps(meta,ensure_ascii=False))
    draft=Framework.model_validate(json.loads(strip_code_fence(raw)))
    return {'planning_mode':'serial','overview':draft.overview,'volumes':[{**v.model_dump(),'chapters':[]} for v in draft.volumes]}

async def generate_blueprint(book,framework,context,instruction=''):
    memory=context.get('memory_status') or {}
    if memory.get('error') or memory.get('pending_chapters'):raise ValueError('历史记忆尚未就绪，请先复核并更新前文章节记忆')
    system=('你是原创连载小说的单章策划。仅规划当前目标章，不规划后面所有章节、不擅自完结。'
      '依据总纲/当前阶段、作者设定、上章结尾和历史证据，让本章有目标、阻碍、行动、转折与阶段结果。'
      '严格区分未来计划与已经发生的事实，不照抄前章事件。不随意改变人物年龄、生死、亲属关系或能力规则。'
      '阅读提供的完整上章原文，先识别已完成事件，不能把已结账款、发现、初次相遇重新安排成本章新事。'
      '允许作者改变后续方向，但不得偷偷改写已发生正文。只输出JSON：'
      '{"title":"本章名","summary":"本章情节梗概，150到350字","ending_hook":"章末悬念或接续点","constraints":["本章不能违反的连续性约束"]}。')
    payload={'book':book,'framework':framework_content(framework),'context':context,'author_instruction':instruction}
    raw,ins,outs,model=await llm_respond({'model_choice':{'kind':'business'},'response_format':{'type':'json_object'}},system+'\n'+method_instructions('plot-design'),json.dumps(payload,ensure_ascii=False))
    return Blueprint.model_validate(json.loads(strip_code_fence(raw))),ins,outs,model

def dependencies(framework,canon,history,book):
    return digest({'framework':framework_content(framework),'canon':canon,'history':history,'book':book})
