"""长任务前置校验、作者确认和幂等入队。公共权限边界由 Ports 统一校验。"""
from uuid import uuid4
from fastapi import HTTPException
from storyclaw.contracts import CapabilityResult
from storyclaw.orchestration.capabilities import get_capability
from app.models import User
from app.services.writing.revisions import chapter_hash

async def execute(ctx, name, arguments):
    db = ctx.db
    book = ctx.book
    chapter = ctx.chapter
    scope = ctx.ports.request.scope
    cap = get_capability(name)
    if not cap.job_kind:
        raise ValueError('此能力尚未实现')
    if cap.job_kind not in ('outline', 'story-design', 'analysis') and (not chapter):
        raise ValueError('请先选择要处理的章节')
    needs_confirmation = name == 'knowledge.ingest' and ctx.ports.request.entry == 'chat' or (name in ('chapter.write', 'chapter.revise') and chapter and bool(chapter.content) and (ctx.ports.request.entry == 'chat'))
    if needs_confirmation:
        if name == 'knowledge.ingest':
            arguments = {**arguments, 'reviewed_hash': chapter_hash(chapter)}
        decision = {'id': str(uuid4()), 'command': name, 'payload': arguments, 'content_hash': chapter_hash(chapter), 'book_title': book.title, 'chapter_title': chapter.title, 'chapter_number': chapter.number, 'summary': '确认审阅当前正文并建立知识索引' if name == 'knowledge.ingest' else '生成将替换本章正文，旧稿保留在版本历史'}
        return CapabilityResult(status='waiting_author', content=decision['summary'], data={'decision': decision})
    from app.services.agent.work_commands import JobInput
    from app.services.agent.work_commands import create_job
    from uuid import uuid5, NAMESPACE_URL
    key = str(uuid5(NAMESPACE_URL, ctx.ports.rid + ':' + name))
    body = {'request_id': key, 'book_id': book.id, 'chapter_id': scope.chapter_id, 'kind': cap.job_kind, **arguments}
    user = await db.get(User, ctx.ports.uid)
    try:
        result = await create_job(JobInput.model_validate(body), user, db)
    except HTTPException as exc:
        if exc.status_code in (400, 409):
            raise ValueError(str(exc.detail)) from exc
        raise
    return CapabilityResult(status='waiting_task', content='任务已提交，切换页面不会取消；完成后请核对结果。', data={'job_id': result['id'], 'job': result})
