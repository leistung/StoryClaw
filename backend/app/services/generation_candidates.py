"""Keep interrupted drafts as owned, version-bound candidates; never auto-adopt failures."""
from fastapi import HTTPException
from sqlalchemy import select
from ..models import Book,Chapter,Message
from ..models.product import WorkJob
from .revisions import current_job_id,chapter_hash,snapshot,assert_editable
async def preserve(db,user,chapter,final,base_hash,thread_id):
    if not final.get('error') and final.get('status')!='error':return
    from storyclaw.metering import active_meter
    meter=active_meter.get();content=final.get('draft_content') or '';jid=current_job_id.get()
    if jid:
        job=await db.get(WorkJob,jid)
        job.result={**(job.result or {}),'error_code':final.get('error_code','model_interrupted'),'thread_id':thread_id,'credits_cost':meter.spent if meter else 0}
        if content:job.result={**job.result,'candidate':{'content':content,'chapter_id':chapter.id,'base_hash':base_hash,'adopted':False,'warning':'生成/修订中断，未审阅通过，请人工核对，不会自动入库'}}
    if content:db.add(Message(user_id=user.id,thread_id=thread_id,role='assistant',content=content,credits_cost=0))
    await db.commit()
    raise HTTPException(503,(final.get('error') or '生成中断')+(' 已保留候选，请在任务中心核对。' if content else ' 未覆盖原正文。'))
async def adopt(db,uid,jid,expected_hash):
    # Same lock order as author edits: book first, then task/candidate.
    first=await db.scalar(select(WorkJob).where(WorkJob.id==jid,WorkJob.user_id==uid))
    if not first:raise HTTPException(404,'任务不存在')
    book=await db.scalar(select(Book).where(Book.id==first.book_id,Book.user_id==uid).with_for_update())
    if not book:raise HTTPException(404,'作品不存在')
    job=await db.scalar(select(WorkJob).where(WorkJob.id==jid).with_for_update().execution_options(populate_existing=True))
    candidate=(job.result or {}).get('candidate')
    if job.status!='failed' or not candidate or not candidate.get('content'):raise HTTPException(409,'没有可采用的中断候选')
    if candidate.get('adopted'):raise HTTPException(409,'候选已经采用')
    chapter=await db.get(Chapter,job.chapter_id)
    if not chapter or chapter.book_id!=book.id:raise HTTPException(404,'章节不存在')
    await assert_editable(db,chapter.id)
    if chapter_hash(chapter)!=expected_hash or candidate['base_hash']!=expected_hash:raise HTTPException(409,'正文已变化，请手动对照，不会覆盖当前版本')
    from .content import reading_html
    from storyclaw.context import count_words
    await snapshot(db,chapter,'interrupted-candidate')
    chapter.content=reading_html(candidate['content']);chapter.word_count=count_words(candidate['content']);chapter.rag_status='pending'
    job.result={**job.result,'candidate':{**candidate,'adopted':True}}
    await db.commit();return {'chapter_id':chapter.id,'words':chapter.word_count,'rag_status':'pending'}
