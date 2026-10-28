"""连续计划控制：共享暂停、恢复、取消和预算校验，避免两套执行规则漂移。"""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.studio import StudioTask
from app.services.jobs.studio_tasks import task_out

async def control_plan(tid, action, budget, user_id, db):
    t = await db.scalar(select(StudioTask).where(StudioTask.id == tid, StudioTask.user_id == user_id).with_for_update())
    if not t:
        raise HTTPException(404, '计划不存在')
    if t.status in ('succeeded', 'cancelled'):
        raise HTTPException(409, '计划已结束')
    if budget is not None:
        if budget < t.spent:
            raise HTTPException(422, '预算不能低于已用积分')
        t.budget = budget
    if action == 'resume':
        if t.status in ('running', 'queued'):
            return task_out(t)
        other = await db.scalar(select(StudioTask.id).where(StudioTask.book_id == t.book_id, StudioTask.id != tid, StudioTask.status.in_(['running', 'queued'])))
        if other:
            raise HTTPException(409, '本书已有运行计划')
        if t.current_job:
            from app.models.product import WorkJob
            job = await db.get(WorkJob, t.current_job)
            if job and job.status in ('failed', 'cancelled'):
                t.current_job = None
                t.result = {**t.result, 'attempt': t.result.get('attempt', 0) + 1}
        t.status = 'queued'
        t.error = None
        t.lease_until = None
    else:
        t.status = 'cancelled' if action == 'cancel' else 'paused'
        # 已开始的推理允许完成；暂停后不再为此计划预约新的调用。
        if t.current_job:
            from app.models.product import WorkJob
            job = await db.get(WorkJob, t.current_job)
            if job and job.status == 'queued':
                job.status = 'cancelled'
                job.error = '所属计划已暂停'
                t.current_job = None
                t.result = {**t.result, 'attempt': t.result.get('attempt', 0) + 1}
    await db.commit()
    return task_out(t)
