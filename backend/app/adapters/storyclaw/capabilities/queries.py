"""作品状态、正文、人物知情与历史证据查询。公共权限边界由 Ports 统一校验。"""
import json
from sqlalchemy import select
from storyclaw.contracts import CapabilityResult
from app.models import Chapter, Outline
from app.models.agent import AgentRun
from app.services.writing.revisions import chapter_hash

async def execute(ctx, name, arguments):
    db = ctx.db
    book = ctx.book
    chapter = ctx.chapter
    scope = ctx.ports.request.scope
    if name == 'author.ask':
        return CapabilityResult(content='请集中补充：\n' + '\n'.join((q['question'] + '：' + ' / '.join(q['options']) for q in arguments['questions'])), data={'artifact': True, 'kind': 'author.question', 'questions': arguments['questions']})
    if name == 'project.status':
        from app.services.writing.serial import blueprint_state
        from storyclaw.workflows.workflow import is_confirmed
        outline = await db.scalar(select(Outline).where(Outline.book_id == book.id))
        content = json.loads(outline.content) if outline and outline.content else {}
        recent = list(await db.scalars(select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.number.desc()).limit(20)))
        data = {'title': book.title, 'genre': book.genre, 'outline_confirmed': is_confirmed(content), 'current_chapter': {'id': chapter.id, 'number': chapter.number, 'words': chapter.word_count, 'rag_status': chapter.rag_status} if chapter else None, 'recent_chapters': [{'id': c.id, 'number': c.number, 'words': c.word_count, 'rag_status': c.rag_status} for c in recent]}
        if chapter:
            data['blueprint'] = await blueprint_state(db, chapter)
        pending = await db.scalars(select(AgentRun).where(AgentRun.user_id == ctx.ports.uid, AgentRun.status == 'waiting_author', AgentRun.request['scope']['book_id'].as_integer() == book.id).order_by(AgentRun.created_at.desc()).limit(8))
        data['pending_plans'] = [{'run_id': r.id, 'command': (r.decision or {}).get('command'), 'summary': (r.decision or {}).get('summary'), 'plan': (r.decision or {}).get('plan')} for r in pending]
        return CapabilityResult(content='作品状态已读取', data=data)
    if name in ('library.status', 'library.search', 'plans.status', 'release.status'):
        from app.models.studio import StorySource
        from app.models.studio import ProjectBaseline
        from app.models.studio import StudioTask
        from app.models.studio import ReleaseRecord
        from app.services.library.library import coverage
        from app.services.library.library import reference_context
        if name == 'library.search':
            from app.services.platform.metering import usage_scope
            async with usage_scope(ctx.ports.uid):
                data = await reference_context(db, ctx.ports.uid, book.id, arguments['query'])
            return CapabilityResult(content='来源证据（不代表读完全书）', data=data)
        if name == 'library.status':
            sources = list(await db.scalars(select(StorySource).where(StorySource.book_id == book.id, StorySource.user_id == ctx.ports.uid)))
            baseline = await db.get(ProjectBaseline, book.id)
            data = {'sources': [await coverage(db, r) for r in sources], 'baseline': {k: getattr(baseline, k) for k in ('mode', 'status', 'cutoff', 'version', 'notes', 'overrides')} if baseline else None}
        elif name == 'plans.status':
            from app.services.jobs.studio_tasks import task_out
            data = {'plans': [task_out(r) for r in await db.scalars(select(StudioTask).where(StudioTask.book_id == book.id).order_by(StudioTask.created_at.desc()).limit(10))]}
        else:
            data = {'releases': [{'id': r.id, 'platform': r.platform, 'status': r.status, 'receipt': r.receipt} for r in await db.scalars(select(ReleaseRecord).where(ReleaseRecord.book_id == book.id).limit(10))]}
        return CapabilityResult(content='已读取本作品真实记录', data=data)
    if name == 'material.read':
        outline = await db.scalar(select(Outline).where(Outline.book_id == book.id))
        return CapabilityResult(content='当前范围资料', data={'book': {'title': book.title, 'intro': (book.intro or '')[:3000]}, 'outline': json.loads(outline.content) if outline and outline.content else {}, 'chapter_text': (chapter.content or '')[:16000] if chapter else '', 'content_hash': chapter_hash(chapter) if chapter else None})
    if name == 'character.knowledge':
        from app.services.knowledge.narrative_state import view
        from sqlalchemy import func
        before = chapter.number if chapter else (await db.scalar(select(func.max(Chapter.number)).where(Chapter.book_id == book.id)) or 0) + 1
        return CapabilityResult(content='人物知情与证据状态（只到本章之前）', data=await view(db, book.id, before, arguments['persona']))
    if name == 'memory.search':
        from app.services.agent.agent_tools import execute_writer_tool
        from app.services.platform.metering import usage_scope
        async with usage_scope(ctx.ports.uid):
            result = await execute_writer_tool('query_memory', {'query': arguments['query']}, ctx.ports.uid, book.id, scope.chapter_id)
        return CapabilityResult(content=result)
