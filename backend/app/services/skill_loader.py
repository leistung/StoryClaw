"""SQL adapter: read authorized manuscript records; composition lives in storyclaw."""
import json
from sqlalchemy import select
from ..models import Book,Chapter,ConfigEntity,Outline
from storyclaw.writing_context import compose_context
from storyclaw.context import find_outline_node,summarize_prev

async def build_write_context(user_id,book_id,chapter_id,db):
    book=await db.get(Book,book_id);chapter=await db.get(Chapter,chapter_id)
    if not book or book.user_id!=user_id or not chapter or chapter.book_id!=book_id:return {}
    row=await db.scalar(select(Outline).where(Outline.book_id==book_id))
    try:outline=json.loads(row.content) if row else {}
    except (ValueError,TypeError):outline={}
    rows=list(await db.scalars(select(ConfigEntity).where(ConfigEntity.book_id==book_id).order_by(ConfigEntity.sort_order,ConfigEntity.id)))
    settings={kind:[{k:getattr(r,k) for k in ('name','category','description','extra_json')} for r in rows if r.entity_type==kind and r.category!='chapter-plan'] for kind in ('character','scene','item','plot','world')}
    history=list(await db.scalars(select(Chapter).where(Chapter.book_id==book_id,Chapter.number<chapter.number).order_by(Chapter.number)))
    prev=next((r for r in history if r.number==chapter.number-1),None)
    plan=next((r for r in rows if r.entity_type=='plot' and r.category=='chapter-plan' and r.name==f'第{chapter.number}章场景任务单'),None)
    from .serial import blueprint_state,inputs
    blueprint=await blueprint_state(db,chapter)
    framework=outline
    if blueprint['plan']:
        outline={**outline,'volumes':[{'name':'当前章纲','chapters':[{'number':chapter.number,**blueprint['plan']}]}]}
    result=await compose_context(user_id=user_id,book_id=book_id,book={'intro':book.intro},chapter={'id':chapter.id,'number':chapter.number,'title':chapter.title,'per_chapter_words':book.per_chapter_words},outline=outline,settings=settings,previous=prev.content if prev else '',allowed=[r.id for r in history if r.rag_status=='loaded'],chapter_numbers={r.id:r.number for r in history},scene_plan=plan.extra_json if plan else {},pending=[r.number for r in history if r.word_count>0 and r.rag_status!='loaded'])
    result['dependency_hash']=(await inputs(db,chapter))[3]
    from storyclaw.serial import digest
    if plan and blueprint['serial'] and (not plan.extra_json or plan.extra_json.get('_dependencies')!=result['dependency_hash'] or plan.extra_json.get('_blueprint_hash')!=digest(result['outline_node'])):result['scene_plan']={}
    result['blueprint_status']={'serial':blueprint['serial'],'confirmed':blueprint['confirmed'],'stale':blueprint['stale']}
    result['framework']=framework
    return result
