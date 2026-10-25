"""SQL/transaction adapters for rolling chapter planning and impact notices."""
import json
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import load_only
from storyclaw.workflows.serial import dependencies
from storyclaw.workflows.serial import digest
from storyclaw.workflows.serial import Blueprint
from storyclaw.workflows.serial import generate_blueprint
from storyclaw.workflows.workflow import is_confirmed
from app.models import Book
from app.models import Chapter
from app.models import ConfigEntity
from app.models import Outline
from app.models import CreditsLedger
from app.services.writing.revisions import chapter_hash
from app.services.writing.revisions import current_job_id
from app.models.product import WorkJob

async def assert_book_idle(db,bid):
    q=select(WorkJob.id).where(WorkJob.book_id==bid,WorkJob.status.in_(['queued','running']))
    if current_job_id.get():q=q.where(WorkJob.id!=current_job_id.get())
    if await db.scalar(q):raise HTTPException(409,'本书有待执行或运行任务，请完成或取消后再改动资料')

async def inputs(db,chapter):
    book=await db.get(Book,chapter.book_id)
    await db.refresh(book)
    row=await db.scalar(select(Outline).where(Outline.book_id==book.id).execution_options(populate_existing=True))
    framework=json.loads(row.content) if row else {}
    canon=list(await db.scalars(select(ConfigEntity).where(ConfigEntity.book_id==book.id,ConfigEntity.entity_type.in_(['character','world','scene','item','plot']),ConfigEntity.category!='chapter-plan').order_by(ConfigEntity.id).execution_options(populate_existing=True)))
    history=list(await db.scalars(select(Chapter).options(load_only(Chapter.id,Chapter.number,Chapter.word_count,Chapter.rag_status)).where(Chapter.book_id==book.id,Chapter.number<chapter.number).order_by(Chapter.number).execution_options(populate_existing=True)))
    meta={k:getattr(book,k) for k in ('title','intro','genre','protagonist_name','protagonist_intro','per_chapter_words')}
    from app.models.studio import ProjectBaseline
    from app.models.studio import PrivateMethod
    methods=list(await db.scalars(select(PrivateMethod).where(PrivateMethod.user_id==book.user_id,PrivateMethod.enabled==True).order_by(PrivateMethod.id)))
    meta['private_methods']=[digest([m.id,m.title,m.content]) for m in methods]
    baseline=await db.get(ProjectBaseline,book.id)
    if baseline:meta['source_baseline']={'version':baseline.version,'hash':baseline.confirmed_hash,'status':baseline.status}
    from app.models.operations import NarrativePolicy
    from app.models.operations import NarrativeFocus
    policy=await db.get(NarrativePolicy,book.id);focus=await db.get(NarrativeFocus,chapter.id)
    meta['narrative_policy_version']=policy.version if policy else 0
    meta['viewpoint']=focus.persona if focus else ''
    from app.services.knowledge.history_prefix import history_digest
    root=await history_digest(db,book.id,chapter.number-1)
    stamp=dependencies(framework,[{'id':r.id,'name':r.name,'type':r.entity_type,'description':r.description,'extra':r.extra_json} for r in canon],[{'prefix_upto':chapter.number-1,'root':root}],meta)
    return framework,meta,history,stamp

async def record(db,chapter):
    return await db.scalar(select(ConfigEntity).where(ConfigEntity.book_id==chapter.book_id,ConfigEntity.entity_type=='workflow',ConfigEntity.name==f'blueprint:{chapter.id}'))

async def blueprint_state(db,chapter):
    framework,_,_,stamp=await inputs(db,chapter)
    row=await record(db,chapter);data=(row.extra_json or {}) if row else {}
    plan=data.get('plan')
    stale=bool(plan) and data.get('dependencies')!=stamp
    confirmed=bool(plan) and not stale and data.get('confirmed_hash')==digest(plan) and data.get('confirmed_dependencies')==stamp
    return {'chapter_id':chapter.id,'serial':framework.get('planning_mode')=='serial','plan':plan,'confirmed':confirmed,'stale':stale,'dependencies':stamp}

async def require_blueprint(db,chapter):
    state=await blueprint_state(db,chapter)
    if state['serial'] and not state['confirmed']:raise HTTPException(409,'请先生成或手写本章章纲并确认；前文或设定变更后需要重新核对章纲')
    return state

async def save_blueprint(db,chapter,plan,stamp):
    row=await record(db,chapter)
    if not row:
        row=ConfigEntity(book_id=chapter.book_id,entity_type='workflow',name=f'blueprint:{chapter.id}',category='chapter-blueprint',description='')
        db.add(row)
    row.extra_json={**(row.extra_json or {}),'plan':plan,'dependencies':stamp}
    await db.flush()
    return row

async def generate_blueprint_job(db,user,chapter,instruction):
    from app.services.platform.skill_loader import build_write_context
    from app.services.writing.planning import require_outline
    from app.services.writing.planning import require_previous_memory
    from app.services.platform.credits import debit
    from app.services.platform.pricing import compute_cost
    await require_outline(db,chapter.book_id);await require_previous_memory(db,chapter)
    framework,meta,history,stamp=await inputs(db,chapter)
    if chapter.number>1 and not any(c.number==chapter.number-1 and c.word_count>0 for c in history):raise HTTPException(409,'连载模式请先完成上一章，不跳过空白章节')
    context=await build_write_context(user.id,chapter.book_id,chapter.id,db)
    plan,ins,outs,model=await generate_blueprint(meta,framework,context,instruction)
    if (await inputs(db,chapter))[3]!=stamp:raise HTTPException(409,'规划期间前文或设定已变化，结果未采用，请重新规划')
    await save_blueprint(db,chapter,plan.model_dump(),stamp)
    cost=compute_cost(model,ins,outs);await debit(db,user,cost)
    db.add(CreditsLedger(user_id=user.id,delta=-cost,reason='chapter-outline',model=model,in_tokens=ins,out_tokens=outs))
    await db.commit()
    return {'chapter_id':chapter.id,'blueprint':plan.model_dump(),'credits_cost':cost,'confirmed':False}

async def invalidate_following(db,chapter,reason,include_self=False):
    q=select(Chapter).where(Chapter.book_id==chapter.book_id,Chapter.number>=chapter.number if include_self else Chapter.number>chapter.number,Chapter.word_count>0)
    for later in list(await db.scalars(q)):
        later.rag_status='pending'
        row=await db.scalar(select(ConfigEntity).where(ConfigEntity.book_id==chapter.book_id,ConfigEntity.entity_type=='workflow',ConfigEntity.name==f'impact:{later.id}'))
        if not row:
            row=ConfigEntity(book_id=chapter.book_id,entity_type='workflow',name=f'impact:{later.id}',category='continuity-impact',description='')
            db.add(row)
        old=row.extra_json or {}
        row.extra_json={'active':True,'chapter_id':later.id,'reason':reason,'source_chapter_id':chapter.id,'source_number':chapter.number}
    await db.flush()

async def acknowledge_index(db,chapter):
    row=await db.scalar(select(ConfigEntity).where(ConfigEntity.book_id==chapter.book_id,ConfigEntity.entity_type=='workflow',ConfigEntity.name==f'impact:{chapter.id}'))
    if row:row.extra_json={**(row.extra_json or {}),'active':False,'reviewed_hash':chapter_hash(chapter)}

async def invalidate_book(db,bid,reason):
    first=await db.scalar(select(Chapter).where(Chapter.book_id==bid).order_by(Chapter.number).limit(1))
    if first:await invalidate_following(db,first,reason,include_self=True)
