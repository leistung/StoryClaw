"""Author actions are host transactions, never model-authorized tool calls."""
from fastapi import HTTPException
from sqlalchemy import select
from storyclaw.contracts import AgentRequest
from app.models import Chapter
from app.models.agent import AgentRun
from app.models.product import WorkJob
from app.services.agent import agent_runs as service
async def owned(rid,u,db,lock=False):
    q=select(AgentRun).where(AgentRun.id==rid,AgentRun.user_id==u.id)
    row=await db.scalar(q.with_for_update() if lock else q)
    if not row:raise HTTPException(404,'请求不存在')
    return row

async def decide(rid,data,u,db):
    row=await owned(rid,u,db,True)
    decision=row.decision or {}
    if data.decision_id!=decision.get('id'):raise HTTPException(409,'确认卡已失效')
    if row.status!='waiting_author':return service.out(row)
    if not data.accept:
        row.status='cancelled';await service.event(db,row,'run.status',{'status':'cancelled'});await db.commit();return service.out(row)
    request=AgentRequest.model_validate(row.request)
    await service.validate_scope(db,u.id,request.scope)
    if decision.get('kind')=='studio_plan':
        from app.services.agent.studio_commands import execute
        task=await execute(db,u,request.scope.book_id,row.id,decision)
        row.status='waiting_task';row.result={'status':'waiting_task','content':'已确认，计划将按约定范围执行。','data':{'plan_id':task['id'],'plan_status':task['status']}}
        await service.event(db,row,'run.status',{'status':row.status,'result':row.result});await db.commit();return service.out(row)
    chapter=await db.get(Chapter,request.scope.chapter_id) if request.scope.chapter_id else None
    from app.services.writing.revisions import chapter_hash
    if decision.get('kind')=='creation_plan':
        from app.models import Book
        from app.services.agent.creation_plans import plan_context
        from storyclaw.workflows.serial import digest
        book=await db.get(Book,request.scope.book_id)
        if digest(await plan_context(db,book))!=decision['context_hash']:
            raise HTTPException(409,'作品资料或大纲已变化，请调整并重新生成计划后再确认')
    elif not chapter or chapter_hash(chapter)!=decision['content_hash']:raise HTTPException(409,'正文已改变，请核对新稿后重新请求')
    from app.services.agent.work_commands import create_job
    from app.services.agent.work_commands import JobInput
    from storyclaw.orchestration.capabilities import get_capability
    from uuid import uuid5,NAMESPACE_URL
    cap=get_capability(decision['command'])
    body={'request_id':str(uuid5(NAMESPACE_URL,row.id+':'+cap.name)),
          'book_id':request.scope.book_id,'chapter_id':chapter.id if chapter else None,'kind':cap.job_kind,**decision['payload']}
    if decision.get('kind')=='creation_plan':body['creation_plan']=decision['plan']
    result=await create_job(JobInput.model_validate(body),u,db)
    # create_job commits its idempotent operation; linking is repeatable after a crash.
    row.status='waiting_task';row.job_id=result['id'];row.result={'status':'waiting_task','content':'已确认并提交任务','data':{'job_id':result['id']}}
    await service.event(db,row,'run.status',{'status':'waiting_task','result':row.result});await db.commit();return service.out(row)

async def cancel(rid,u,db):
    row=await owned(rid,u,db,True)
    if row.status in service.TERMINAL:return service.out(row)
    plan_id=((row.result or {}).get('data') or {}).get('plan_id')
    if plan_id:
        from app.services.jobs.studio_controls import control_plan
        await control_plan(plan_id,'pause',None,u.id,db)
    if row.job_id:
        job=await db.scalar(select(WorkJob).where(WorkJob.id==row.job_id,WorkJob.user_id==u.id).with_for_update())
        if job and job.status=='running':raise HTTPException(409,'后台任务已执行，请等待当前步骤结束；不会自动启动下一步')
        if job and job.status=='queued':job.status='cancelled';job.finished_at=service.now()
    row.status='cancelled';await service.event(db,row,'run.status',{'status':'cancelled'});await db.commit();return service.out(row)
