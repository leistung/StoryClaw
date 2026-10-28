"""Bridge worker observations to the owning durable run event log."""
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.agent import AgentRun
from app.models.product import WorkJob

async def emit_plan(tid,kind,payload):
    if kind in ('draft','message.delta'):return
    from app.services.agent.agent_runs import event
    async with AsyncSessionLocal() as db:
        rows=await db.scalars(select(AgentRun).where(AgentRun.result['data']['plan_id'].as_string()==tid).with_for_update())
        for row in rows:await event(db,row,kind,{**payload,'plan_id':tid})
        await db.commit()

async def emit(jid,kind,payload):
    if kind in ('draft','message.delta'):return
    from app.services.agent.agent_runs import event
    from uuid import uuid5,NAMESPACE_URL
    async with AsyncSessionLocal() as db:
        rows=list(await db.scalars(select(AgentRun).where(AgentRun.job_id==jid).with_for_update()))
        job=await db.get(WorkJob,jid)
        if job and job.payload.get('studio_plan'):
            linked=list(await db.scalars(select(AgentRun).where(AgentRun.user_id==job.user_id,
                AgentRun.result['data']['plan_id'].as_string()==job.payload['studio_plan']).with_for_update()))
            rows.extend(r for r in linked if r.id not in {x.id for x in rows})
        # Enqueue commits before linking the run: include that short race window.
        if not rows:
            job=await db.get(WorkJob,jid)
            if job:
                candidates=list(await db.scalars(select(AgentRun).where(AgentRun.user_id==job.user_id,
                    AgentRun.status.in_(['running','waiting_author'])).with_for_update()))
                for r in candidates:
                    command=(r.decision or {}).get('command') or r.request.get('command')
                    if command and str(uuid5(NAMESPACE_URL,r.id+':'+command))==job.request_id:rows.append(r)
        for row in rows:
            await event(db,row,kind,{**payload,'job_id':jid})
        await db.commit()
