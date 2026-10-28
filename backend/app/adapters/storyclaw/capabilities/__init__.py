"""显式能力路由表：新增非任务能力必须登记，避免巨型条件分支。"""
from dataclasses import dataclass
from typing import TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Book, Chapter
from app.models.agent import AgentRun

if TYPE_CHECKING:
    from app.adapters.storyclaw.agent import BackendStoryPorts
from storyclaw.orchestration.capabilities import get_capability
from . import materials, planning, queries, creative, jobs

@dataclass(frozen=True)
class CapabilityContext:
    """单次调用的授权上下文；不可保存为跨用户的全局状态。"""
    ports: "BackendStoryPorts"
    db: AsyncSession
    book: Book
    chapter: Chapter | None
    run: AgentRun

HANDLERS = {
    'skills.list': materials.execute,
    'skills.read': materials.execute,
    'setting.read': materials.execute,
    'setting.update': materials.execute,
    'creation.revise': planning.execute,
    'plans.create': planning.execute,
    'plans.resume': planning.execute,
    'framework.draft': planning.execute,
    'setting.draft': planning.execute,
    'author.ask': queries.execute,
    'project.status': queries.execute,
    'library.status': queries.execute,
    'library.search': queries.execute,
    'plans.status': queries.execute,
    'release.status': queries.execute,
    'material.read': queries.execute,
    'character.knowledge': queries.execute,
    'memory.search': queries.execute,
    'idea.brainstorm': creative.execute,
    'title.suggest': creative.execute,
    'text.polish': creative.execute,
    'text.continue': creative.execute,
    'text.scene_enhance': creative.execute,
    'text.dialogue_polish': creative.execute,
}

def handler_for(name):
    capability = get_capability(name)
    if name in HANDLERS:
        return HANDLERS[name]
    if capability.job_kind:
        return jobs.execute
    raise ValueError('能力尚未登记执行器：' + name)
