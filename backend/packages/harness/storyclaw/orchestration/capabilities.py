"""One capability name for both button commands and model tool calls."""
from dataclasses import dataclass
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Query(Empty):
    query: str = Field(min_length=1,max_length=1000)
class Draft(Empty):
    prompt: str = Field(default='',max_length=12000)
class Framework(Draft):
    planning_mode: str = Field(default='serial',pattern='^(serial|fixed)$')
class Design(Draft):
    design_type: str = Field(default='character',pattern='^(character|world|plot)$')
class Analysis(Empty):
    skill: str = Field(default='book-summary',pattern='^(book-summary|consistency-check|character-development|plot-planning)$')
    start: int = Field(default=1,ge=1)
    end: int = Field(default=10,ge=1)
class Index(Empty):
    reviewed_hash: str = Field(min_length=32,max_length=64,pattern='^[a-f0-9]+$')

class CharacterKnowledge(Empty):
    persona:str=Field(default='',max_length=120)

class Choice(Empty):
    question: str=Field(min_length=1,max_length=300)
    options: list[Annotated[str,Field(min_length=1,max_length=200)]]=Field(min_length=2,max_length=6)
class Questions(Empty):
    questions: list[Choice]=Field(min_length=1,max_length=3)

class Creative(Empty):
    instruction: str = Field(min_length=1,max_length=6000)
class Edit(Creative):
    selected_text: str = Field(default='',max_length=6000)
class ContinueDraft(Creative):
    max_words:int=Field(default=600,ge=50,le=1500)

class SkillName(Empty):
    name:str=Field(min_length=1,max_length=80)
    reference:str=Field(default='',max_length=200,description='留空读取SKILL.md；按需读取时填写reference_files中列出的references/*.md路径')
class ReviseCreation(Empty):
    run_id:str=Field(min_length=36,max_length=36)
    feedback:str=Field(min_length=1,max_length=6000)
class StudioPlan(Empty):
    kind:str=Field(default='serial',pattern='^(serial|source-analysis)$')
    start:int=Field(default=1,ge=1)
    end:int=Field(default=3,ge=1)
    budget:int=Field(ge=1,le=1000000)
    source_id:str|None=Field(default=None,max_length=36)
    auto_adopt:bool=False
    instruction:str=Field(default='',max_length=6000)
class ResumePlan(Empty):
    plan_id:str=Field(min_length=36,max_length=36)
    budget:int=Field(ge=1,le=1000000)
class SettingQuery(Empty):
    entity_type:str=Field(default='',pattern='^(|character|world|scene|item|plot)$')
    keyword:str=Field(default='',max_length=128)
class SettingEdit(Empty):
    entity_id:int=Field(gt=0)
    expected_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    name:str=Field(min_length=1,max_length=128)
    category:str|None=Field(default=None,max_length=50)
    description:str=Field(min_length=1,max_length=12000)

@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    schema: type[BaseModel]
    job_kind: str | None = None
    confirmation: bool = False

CATALOG = {
 c.name:c for c in [
 Capability('author.ask','一次集中询问最多3个必要问题，提供可点击选项并允许自填；不代替创作确认',Questions),
 Capability('project.status','查看当前作品的真实章纲、正文和记忆状态',Empty),
 Capability('character.knowledge','查看当前章开始前的人物知情、信念、证据与被隐去的秘密数量',CharacterKnowledge),
 Capability('library.status','查看本作品只读来源、接管基线和覆盖程度',Empty),
 Capability('library.search','查询作者确认截止范围内的原作和接管证据',Query),
 Capability('plans.status','查看本作品连续计划、暂停原因及预算',Empty),
 Capability('plans.create','拟订有限连续写作或来源分析的执行范围和预算，等待作者确认；不能直接授权自动采用',StudioPlan),
 Capability('plans.resume','提议恢复本作品已有计划，展示预算并等待作者确认',ResumePlan),
 Capability('creation.revise','根据作者补充重新拟订当前作品待确认的生成计划，run_id必须来自实际计划记录',ReviseCreation),
 Capability('skills.list','查看可用创作Skill的方法目录',Empty),
 Capability('skills.read','读取创作Skill的方法、约束与版本；用reference按需读取其登记的详细参考和示例',SkillName),
 Capability('release.status','查看本作品冻结投稿包与人工回执，不代替外站发布',Empty),
 Capability('material.read','读取当前章节和本书确认规划，不读取其他书',Empty),
 Capability('memory.search','检索本书允许历史的有效正文证据',Query),
 Capability('framework.draft','生成总方向/阶段草案，等待作者确认',Framework,'outline'),
 Capability('setting.draft','生成世界观/角色/情节草案，等待作者采用',Design,'story-design'),
 Capability('setting.read','查询本作品角色/世界观/场景/物品/情节档案，返回真实ID、内容与版本摘要',SettingQuery),
 Capability('setting.update','依据setting.read的真实ID和版本提出档案修改候选，保留旧值，作者采用后保存；不直接改正文',SettingEdit),
 Capability('chapter.plan','生成当前章纲草案，等待作者确认',Draft,'chapter-outline'),
 Capability('chapter.scenes','生成确认章纲的可选场景任务单',Empty,'scene-plan'),
 Capability('chapter.revise','按作者要求修改当前章，已有正文先请求确认并保留旧版本',Draft,'revise',True),
 Capability('chapter.write','生成并保存当前章；已有正文需作者确认覆盖',Draft,'generate',True),
 Capability('idea.brainstorm','根据当前书籍约束生成多个创意候选，不改正文',Creative),
 Capability('title.suggest','生成当前书籍或章节标题候选，不自动改名',Creative),
 Capability('text.polish','润色作者引用的本章选区；有绑定引用时selected_text可省略，后端解析真实选区。返回候选不覆盖正文',Edit),
 Capability('text.continue','读取本章全文，在作者绑定光标位置续写；无光标引用则接章末。按作者目标设置max_words，返回可插入候选',ContinueDraft),
 Capability('text.scene_enhance','增强本章指定场景片段的表达，保留事实',Edit),
 Capability('text.dialogue_polish','打磨本章指定对白片段，保留信息',Edit),
 Capability('book.analyze','生成指定范围的分析/摘要报告，不修改正文',Analysis,'analysis'),
 Capability('knowledge.ingest','对作者确认的正文版本建立知识索引',Index,'index',True),
 ]
}

def get_capability(name: str) -> Capability:
    if name not in CATALOG: raise ValueError('未知或尚未实现的能力：'+name)
    return CATALOG[name]

def job_command(kind: str) -> str:
    return next(c.name for c in CATALOG.values() if c.job_kind==kind)

def model_tools() -> list[dict]:
    return [{'type':'function','function':{'name':c.name.replace('.','__'),
             'description':c.description,'parameters':c.schema.model_json_schema()}}
            for c in CATALOG.values()]
