"""Resumable source analysis and bounded serial orchestration; no model inference code."""
import asyncio,json,logging
from datetime import datetime,timezone,timedelta
from uuid import uuid4,uuid5,NAMESPACE_URL
from fastapi import HTTPException
from sqlalchemy import select,update,func
from ..database import AsyncSessionLocal
from ..models import User,Chapter,Book,CreditsLedger
from ..models.studio import StudioTask,SourceChapter,StorySource,ProjectBaseline
from ..models.product import WorkJob
from .library import own_book,own_source
from .work_commands import create_job,JobInput
from .revisions import chapter_hash

def now():return datetime.now(timezone.utc)
def task_out(t):return {k:getattr(t,k) for k in ('id','book_id','kind','status','payload','result','error','budget','spent','current_job')}

async def create_task(db,uid,bid,kind,request_id,payload,budget):
    await own_book(db,uid,bid,True)
    existing=await db.scalar(select(StudioTask).where(StudioTask.user_id==uid,StudioTask.request_id==request_id))
    if existing:
        if existing.book_id!=bid or existing.kind!=kind or existing.payload!=payload or existing.budget!=budget:raise HTTPException(409,'请求编号已用于其他计划')
        return existing
    active=await db.scalar(select(StudioTask.id).where(StudioTask.book_id==bid,StudioTask.status.in_(['queued','running'])))
    if active:raise HTTPException(409,'本作品已有长期计划，请先暂停或完成')
    if kind=='source-analysis':
        source=await own_source(db,uid,payload['source_id'])
        if source.status=='revoked' or not source.rights.get('ai_allowed'):raise HTTPException(409,'来源未允许模型处理或已停用')
        count=await db.scalar(select(func.count()).select_from(SourceChapter).where(SourceChapter.source_id==source.id))
        if not 1<=payload['start']<=payload['end']<=count:raise HTTPException(422,'分析范围不在来源章节内')
    task=StudioTask(id=str(uuid4()),user_id=uid,book_id=bid,request_id=request_id,kind=kind,payload=payload,budget=budget,spent=0,status='queued',result={})
    db.add(task);await db.commit();return task

async def analyze_step(tid):
    from storyclaw.workflows.library import analyze_source_chapter,index_source_segment
    from .metering import usage_scope
    async with AsyncSessionLocal() as db:
        task=await db.get(StudioTask,tid);source=await own_source(db,task.user_id,task.payload['source_id'])
        if source.status=='revoked' or not source.rights.get('ai_allowed'):raise HTTPException(409,'来源权限已撤销')
        row=await db.scalar(select(SourceChapter).where(SourceChapter.source_id==source.id,SourceChapter.number>=task.payload['start'],SourceChapter.number<=task.payload['end'],SourceChapter.analysis_status!='ready').order_by(SourceChapter.number).limit(1))
        if not row:
            task.status='succeeded';task.result={**task.result,'completed':True};await db.commit();return
        if row.analysis_status in ('unknown','running'):raise HTTPException(409,'上一分析结果不确定，请核对后显式重置该章节')
        parts=(row.analysis or {}).get('segments',[]);offset=sum(p['length'] for p in parts);text=row.content[offset:offset+6000]
        if not text:row.analysis_status='ready';await db.commit();return
        row.analysis_status='running';cid=row.id;uid=task.user_id;title=row.title;await db.commit()
    try:
        async with usage_scope(uid,plan_id=tid) as meter:
            digest,ins,outs,model=await analyze_source_chapter(title,text)
            from ..models.studio import SourceIndex
            from secrets import randbits
            async with AsyncSessionLocal() as db:
                index=SourceIndex(source_chapter_id=cid,offset=offset,physical_id=-(randbits(46)+1),status='staging',result={});db.add(index);await db.commit();iid=index.id;physical=index.physical_id
            index_result=await index_source_segment(uid,'source_'+source.id.replace('-',''),physical,text,digest)
            async with AsyncSessionLocal() as db:
                index=await db.get(SourceIndex,iid);index.result=index_result;index.status='active' if not index_result.get('error') and index_result.get('stores',{}).get('vector')=='milvus' and index_result.get('stores',{}).get('graph')=='neo4j' else 'failed'
                from .cleanup import enqueue
                if index.status!='active':await enqueue(db,'index',{'user_id':uid,'namespace':'source_'+source.id.replace('-',''),'physical_id':physical},24)
                await db.commit()
                if index.status!='active':raise HTTPException(502,index_result.get('error') or '来源索引未完整就绪')
    except BaseException:
        async with AsyncSessionLocal() as db:
            r=await db.get(SourceChapter,cid);r.analysis_status='unknown';r.error='上游结果未采用，请核对回执后显式重试';await db.commit()
        raise
    async with AsyncSessionLocal() as db:
        task=await db.get(StudioTask,tid);r=await db.get(SourceChapter,cid)
        parts.append({'offset':offset,'length':len(text),'digest':digest,'model':model,'cost':meter.spent})
        r.analysis={'segments':parts,'summary':'\n'.join(p['digest']['summary'] for p in parts)[:4000],
            'facts':[f for p in parts for f in p['digest']['facts']],'unresolved':[x for p in parts for x in p['digest']['unresolved']]}
        r.analysis_status='ready' if offset+len(text)>=len(r.content) else 'pending';r.error=None
        task.result={**task.result,'last_chapter':r.number};await db.commit()

async def serial_step(tid):
    from .serial import blueprint_state,inputs,save_blueprint
    from storyclaw.serial import digest
    async with AsyncSessionLocal() as db:
        task=await db.scalar(select(StudioTask).where(StudioTask.id==tid).with_for_update())
        if task.status not in ('queued','running'):return
        user=await db.get(User,task.user_id);book=await db.get(Book,task.book_id)
        baseline=await db.get(ProjectBaseline,book.id)
        if baseline and baseline.status!='baseline_ready' and task.payload['auto_adopt']:
            task.status='waiting_author';task.error='接管资料仅辅助就绪，自动采用前需要完成分析并重新确认基线';await db.commit();return
        number=task.result.get('next',task.payload['start'])
        if number>task.payload['end']:
            task.status='succeeded';task.error=None;await db.commit();return
        chapter=await db.scalar(select(Chapter).where(Chapter.book_id==book.id,Chapter.number==number))
        if not chapter:
            chapter=Chapter(book_id=book.id,number=number,title=f'第{number}章',content='',word_count=0,rag_status='pending');db.add(chapter);await db.flush()
        state=await blueprint_state(db,chapter)
        phase=task.result.get('phase','plan')
        if task.current_job:
            job=await db.get(WorkJob,task.current_job)
            if job.status in ('queued','running'):return
            if job.status!='succeeded':task.status='paused';task.error=job.error or '任务已中止';await db.commit();return
            if not job.payload.get('studio_plan'):task.spent+=int((job.result or {}).get('credits_cost',0))
            task.current_job=None
            phase={'plan':'confirm','write':'review','index':'next'}[phase]
            task.result={**task.result,'phase':phase}
        if phase=='confirm':
            if not state['confirmed']:
                if not task.payload['auto_adopt'] or not state['plan'] or state['stale']:
                    task.status='waiting_author';task.error='请核对并确认当前章纲后恢复计划';await db.commit();return
                row=await save_blueprint(db,chapter,state['plan'],state['dependencies'])
                row.extra_json={**row.extra_json,'confirmed_hash':digest(state['plan']),'confirmed_dependencies':state['dependencies'],'source_plan':task.id}
            phase='write'
        if phase=='review' and chapter.rag_status=='loaded':phase='next'
        if phase=='review':
            if not task.payload['auto_adopt']:
                task.status='waiting_author';task.error='请审阅本章，确认入库后恢复计划';await db.commit();return
            feedback=(job.result or {}).get('review_feedback','') if task.current_job is None and 'job' in locals() else ''
            if any(x in feedback for x in ('重复风险','偏离目标','请继续修订')):
                task.status='waiting_author';task.error='正文仍有审阅问题，请核对后手动入库';await db.commit();return
            phase='index'
        if phase=='next':
            task.result={**task.result,'next':number+1,'phase':'plan'};await db.commit();return
        # Reuse existing confirmed body without overwriting it; existing pending text needs review.
        if chapter.word_count and phase in ('plan','write'):
            if chapter.rag_status=='loaded':task.result={**task.result,'next':number+1,'phase':'plan'};await db.commit();return
            task.status='waiting_author';task.error='本章已有正文，请审阅入库；不会自动覆盖';await db.commit();return
        if phase=='plan' and state['confirmed']:phase='write'
        if phase=='write' and state.get('plan') and chapter.title==f'第{number}章':
            chapter.title=state['plan']['title'][:255];await db.flush()
        if task.spent>=task.budget:task.status='paused';task.error='计划预算已用完';await db.commit();return
        kind={'plan':'chapter-outline','write':'generate','index':'index'}[phase]
        key=str(uuid5(NAMESPACE_URL,f'{task.id}:{number}:{phase}:{task.result.get("attempt",0)}'))
        body={'book_id':book.id,'chapter_id':chapter.id,'kind':kind,'request_id':key,'prompt':task.payload.get('instruction','')}
        if kind=='index':body['reviewed_hash']=chapter_hash(chapter)
        # Per-call global budget enforcement is attached to WorkJob below.
        result=await create_job(JobInput.model_validate(body),user,db,plan_id=task.id)
        task.current_job=result['id'];task.status='running';task.error=None;task.result={**task.result,'phase':phase,'next':number}
        await db.commit()

async def poll_once(task_id=None):
    async with AsyncSessionLocal() as db:
        expired=list(await db.scalars(select(StudioTask).where(StudioTask.status=='running',StudioTask.lease_until<now()).with_for_update(skip_locked=True)))
        for task in expired:
            task.status='paused';task.error='执行进程中断，请核对当前步骤后恢复，不自动重试模型'
            reserve=(task.result or {}).get('reservation',0)
            if reserve:
                await db.execute(update(User).where(User.id==task.user_id).values(credits_balance=User.credits_balance+reserve))
                task.result={**task.result,'reservation':0,'usage_known':False}
        query=select(StudioTask).where(StudioTask.status.in_(['queued','running']),((StudioTask.lease_until==None)|(StudioTask.lease_until<now())))
        if task_id:query=query.where(StudioTask.id==task_id)
        task=await db.scalar(query.order_by(StudioTask.created_at).with_for_update(skip_locked=True).limit(1))
        if not task:await db.commit();return False
        task.status='running';task.lease_until=now()+timedelta(minutes=5);tid=task.id;kind=task.kind;await db.commit()
    try:
        if kind=='source-analysis':await analyze_step(tid)
        else:await serial_step(tid)
    except asyncio.CancelledError:raise
    except Exception as exc:
        logging.getLogger(__name__).exception('Studio task failed id=%s',tid)
        async with AsyncSessionLocal() as db:
            task=await db.get(StudioTask,tid);task.status='paused';task.error=str(exc.detail) if isinstance(exc,HTTPException) else '当前步骤失败，请核对上游配置与执行记录后恢复';await db.commit()
    finally:
        async with AsyncSessionLocal() as db:
            task=await db.get(StudioTask,tid)
            if task:
                if task.status=='running':task.status='queued'
                task.lease_until=None;await db.commit()
    return True

async def queue_loop():
    while True:
        try:
            from .metering import reclaim_expired
            await reclaim_expired()
            if not await poll_once():await asyncio.sleep(2)
            else:await asyncio.sleep(.2)
        except asyncio.CancelledError:raise
        except Exception:logging.getLogger(__name__).exception('Studio queue failed');await asyncio.sleep(3)
