"""Scoped studio proposals; only a real author decision starts/resumes work."""
from uuid import uuid4,uuid5,NAMESPACE_URL
from fastapi import HTTPException
from sqlalchemy import select
from app.models.studio import StudioTask

async def propose(db,uid,bid,name,args,title):
    if name=='plans.create':
        if args['end']<args['start'] or (args['kind']=='serial' and args['end']-args['start']>100):raise ValueError('范围无效，单次连续写作最多101章')
        if args['kind']=='source-analysis':
            from app.services.library.library import own_source
            source=await own_source(db,uid,args['source_id']) if args.get('source_id') else None
            if not source or source.status=='revoked' or not source.rights.get('ai_allowed'):raise ValueError('请选择已允许模型处理的有效来源')
        summary=f"{'连续写作' if args['kind']=='serial' else '来源分析'}：第{args['start']}–{args['end']}章，总预算{args['budget']}积分。"+('授权在此范围内自动采用章纲与审阅通过正文，并入库。' if args['auto_adopt'] else '章纲和正文仍需作者审阅确认。')
    else:
        task=await db.get(StudioTask,args['plan_id'])
        if not task or task.user_id!=uid or task.book_id!=bid:raise HTTPException(404,'本作品的计划不存在')
        if task.status in ('succeeded','cancelled'):raise ValueError('计划已结束，不能恢复')
        if args['budget']<task.spent:raise ValueError('总预算不能低于已消耗积分')
        summary=f"恢复计划 {task.id}；第{task.payload['start']}–{task.payload['end']}章，总预算{args['budget']}积分，已用{task.spent}积分。"
    return {'id':str(uuid4()),'kind':'studio_plan','command':name,'payload':args,'book_title':title,'summary':summary}

async def execute(db,user,bid,rid,decision):
    from app.services.jobs.studio_tasks import create_task,task_out
    from storyclaw.orchestration.capabilities import get_capability
    args=get_capability(decision['command']).schema.model_validate(decision['payload']).model_dump()
    if decision['command']=='plans.create':
        task=await create_task(db,user.id,bid,args['kind'],str(uuid5(NAMESPACE_URL,rid+':studio')),
             {k:args[k] for k in ('start','end','source_id','auto_adopt','instruction')},args['budget'])
    else:
        # Reuse the existing control policy after verifying this run's book scope.
        task=await db.scalar(select(StudioTask).where(StudioTask.id==args['plan_id'],StudioTask.user_id==user.id,StudioTask.book_id==bid))
        if not task:raise HTTPException(404,'本作品的计划不存在')
        from app.services.jobs.studio_controls import control_plan
        result=await control_plan(task.id,'resume',args['budget'],user.id,db)
        return result
    return task_out(task)
