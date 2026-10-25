"""One capability name for both button commands and model tool calls."""
from dataclasses import dataclass
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

@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    schema: type[BaseModel]
    job_kind: str | None = None
    confirmation: bool = False

CATALOG = {
 c.name:c for c in [
 Capability('project.status','查看当前作品的真实章纲、正文和记忆状态',Empty),
 Capability('material.read','读取当前章节和本书确认规划，不读取其他书',Empty),
 Capability('memory.search','检索本书允许历史的有效正文证据',Query),
 Capability('framework.draft','生成总方向/阶段草案，等待作者确认',Framework,'outline'),
 Capability('setting.draft','生成世界观/角色/情节草案，等待作者采用',Design,'story-design'),
 Capability('chapter.plan','生成当前章纲草案，等待作者确认',Draft,'chapter-outline'),
 Capability('chapter.scenes','生成确认章纲的可选场景任务单',Empty,'scene-plan'),
 Capability('chapter.write','生成并保存当前章；已有正文需作者确认覆盖',Draft,'generate',True),
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
