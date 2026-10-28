"""平台到 AI 包的端口适配：只维护公共授权、事件和模型/生命周期接入。"""
from fastapi import HTTPException
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import User
from app.models import Book
from app.models import Chapter
from app.models.agent import AgentRun
from app.services.agent import agent_runs

class BackendStoryPorts:

    def __init__(self, rid, uid, request):
        self.rid = rid
        self.uid = uid
        self.request = request

    async def emit(self, kind, payload):
        await agent_runs.append(self.rid, self.uid, kind, payload)
        from storyclaw.runtime.deps import get_stream_sink
        sink = get_stream_sink()
        if sink is not None and getattr(sink, 'run_id', None) != self.rid:
            await sink(kind, payload)

    async def execute(self, name, arguments):
        from storyclaw.runtime.deps import get_stream_sink, set_stream_sink
        previous = get_stream_sink()

        async def sink(kind, payload):
            if kind not in ('draft', 'message.delta'):
                await agent_runs.append(self.rid, self.uid, kind, payload)
        sink.run_id = self.rid
        sink.drafts_enabled = False
        set_stream_sink(sink)
        try:
            return await self._execute(name, arguments)
        finally:
            set_stream_sink(previous)

    async def _execute(self, name, arguments):
        scope = self.request.scope
        async with AsyncSessionLocal() as db:
            # 每次工具调用重新校验归属和正文引用，不能信任模型传入的资源标识。
            await agent_runs.validate_scope(db, self.uid, scope)
            row = await db.get(AgentRun, self.rid)
            if row.status == 'cancelled':
                raise HTTPException(409, '请求已取消')
            if not scope.book_id:
                raise ValueError('请先打开一本作品，再使用此能力；首页选题请使用开书讨论。')
            book = await db.get(Book, scope.book_id)
            chapter = await db.get(Chapter, scope.chapter_id) if scope.chapter_id else None
            from app.services.agent.manuscript_references import validate_references
            await validate_references(db, self.request)
            from app.adapters.storyclaw.capabilities import CapabilityContext, handler_for
            return await handler_for(name)(CapabilityContext(self, db, book, chapter, row), name, arguments)

    async def model_turn(self, messages, tools):
        import time
        started = time.monotonic()
        await self.emit('step.started', {'name': 'lead.model', 'label': '理解需求，选择下一步能力', 'message_count': len(messages), 'tool_count': len(tools)})
        from app.services.platform.llm import build_llm_from_choice
        from app.services.platform.metering import usage_scope
        from storyclaw.models.metering import MeteredModel
        from storyclaw.orchestration.model import generate_lead_turn
        client, model = await build_llm_from_choice({'kind': 'business'})
        usage = {}
        meter = None
        try:
            async with usage_scope(self.uid, run_id=self.rid) as meter:

                async def delta(text):
                    await self.emit('message.delta', {'text': text})

                async def record_usage(data):
                    usage.update(data)
                result = await generate_lead_turn(MeteredModel(client, model, meter), messages, tools, delta, record_usage)
                await self.emit('step.completed', {'name': 'lead.model', 'label': '本轮响应已返回', 'model': model, 'tools': [c.name for c in result.calls], 'duration_ms': round((time.monotonic() - started) * 1000), 'usage': usage})
                return result
        finally:
            if meter and meter.calls:
                async with AsyncSessionLocal() as db:
                    run = await db.scalar(select(AgentRun).where(AgentRun.id == self.rid).with_for_update())
                    await agent_runs.event(db, run, 'usage.updated', {'model': model, 'credits_cost': meter.spent, 'usage_known': bool(usage)})
                    await db.commit()

    async def lifecycle(self, action, run_id, data=None):
        from app.services.agent.agent_decisions import owned
        from app.services.agent.agent_decisions import decide
        from app.services.agent.agent_decisions import cancel
        from types import SimpleNamespace
        from app.models.agent import AgentEvent
        async with AsyncSessionLocal() as db:
            user = await db.get(User, self.uid)
            if not user:
                raise HTTPException(401, '登录失效')
            if action == 'decision':
                return await decide(run_id, SimpleNamespace(**data), user, db)
            if action == 'cancel':
                return await cancel(run_id, user, db)
            row = await owned(run_id, user, db)
            if action == 'status':
                return agent_runs.out(row)
            if action == 'events':
                after = int((data or {}).get('after_seq', 0))
                if after < 0:
                    raise HTTPException(422, '事件位置无效')
                rows = await db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.seq > after).order_by(AgentEvent.seq).limit(200))
                return [{'id': e.id, 'run_id': e.run_id, 'seq': e.seq, 'type': e.type, 'payload': e.payload} for e in rows]
            raise ValueError('未知运行操作')
