"""生成计划、反馈调整和连续计划提议。公共权限边界由 Ports 统一校验。"""
from uuid import uuid4
from storyclaw.contracts import CapabilityResult

async def execute(ctx, name, arguments):
    db = ctx.db
    book = ctx.book
    row = ctx.run
    if name == 'creation.revise':
        from app.services.agent.agent_runs import revise_creation
        await revise_creation(db, ctx.ports.uid, book.id, arguments['run_id'], arguments['feedback'], ctx.ports.rid)
        return CapabilityResult(content='已按你的补充安排重新拟订计划，更新后会显示新的确认卡。', data={'artifact': True, 'kind': 'creation.revised', 'run_id': arguments['run_id']})
    if name in ('plans.create', 'plans.resume'):
        from app.services.agent.studio_commands import propose
        decision = await propose(db, ctx.ports.uid, book.id, name, arguments, book.title)
        return CapabilityResult(status='waiting_author', content=decision['summary'], data={'decision': decision})
    if name in ('framework.draft', 'setting.draft'):
        from app.services.agent.creation_plans import prepare
        from storyclaw.workflows.serial import digest
        from app.services.platform.metering import usage_scope
        from app.services.platform.platform import refresh_configs
        await refresh_configs(db)
        async with usage_scope(ctx.ports.uid, run_id=ctx.ports.rid):
            plan, context, estimate = await prepare(db, book, name, arguments, row.decision or {}, ctx.ports.emit)
        decision = {'id': str(uuid4()), 'kind': 'creation_plan', 'command': name, 'payload': arguments, 'plan': plan.model_dump(), 'context_hash': digest(context), 'estimate': estimate, 'book_title': book.title, 'summary': '请核对生成规模和具体内容；可以补充要求后调整计划，确认后才开始正式生成。'}
        return CapabilityResult(status='waiting_author', content=decision['summary'], data={'decision': decision})
