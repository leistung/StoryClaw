"""Author-approved outline snapshot used by dependent writing tasks."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import load_only
from app.models import Outline
from app.models.product import WorkJob
from app.services.writing.revisions import current_job_id

from storyclaw.workflows.workflow import outline_hash
from storyclaw.workflows.workflow import is_confirmed
from storyclaw.workflows.workflow import pending_history

async def require_outline(db,bid):
    row=await db.scalar(select(Outline).where(Outline.book_id==bid))
    try:content=json.loads(row.content) if row else {}
    except (ValueError,TypeError):content={}
    if not is_confirmed(content):raise HTTPException(409,'请先在大纲页保存并确认大纲，再进行情节规划、场景任务单或 AI 章节写作')
    return outline_hash(content)

async def assert_planning_editable(db,bid):
    q=select(WorkJob.id).where(WorkJob.book_id==bid,WorkJob.status.in_(['queued','running']),WorkJob.kind.in_(['outline','generate','revise','scene-plan','analysis','story-design','chapter-outline']))
    if current_job_id.get():q=q.where(WorkJob.id!=current_job_id.get())
    if await db.scalar(q):raise HTTPException(409,'本书有排队或执行中的创作任务，请完成或取消后再修改大纲')


async def require_previous_memory(db,chapter):
    from app.models import Chapter
    rows=await db.scalars(select(Chapter).options(load_only(Chapter.id,Chapter.number,Chapter.word_count,Chapter.rag_status)).where(Chapter.book_id==chapter.book_id,Chapter.number<chapter.number))
    rows=list(rows)
    frame=await db.scalar(select(Outline).where(Outline.book_id==chapter.book_id))
    serial=bool(frame and json.loads(frame.content).get('planning_mode')=='serial')
    if serial and chapter.number>1 and not any(r.number==chapter.number-1 and r.word_count>0 for r in rows):raise HTTPException(409,'请先完成上一章，连载写作不能跳过空白章节')
    from app.services.library.library import imported_exemptions
    exempt=await imported_exemptions(db,chapter.book_id)
    missing=pending_history([{'number':r.number,'word_count':r.word_count,'rag_status':r.rag_status} for r in rows if r.id not in exempt])
    if missing:raise HTTPException(409,'请先审阅并更新历史章节故事记忆：'+str(missing))
