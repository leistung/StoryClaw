"""SQL outbox for private object and retired index cleanup; retries never invoke models."""
import asyncio,hashlib,logging
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from sqlalchemy import select,update
from sqlalchemy.dialects.postgresql import insert
from app.database import AsyncSessionLocal
from app.models.operations import CleanupTask
from app.models.operations import SourceBlob
from app.models.studio import IndexManifest
from app.models.studio import SourceIndex
from app.models.studio import SourceChapter
from app.models.studio import StorySource
from app.models import Book
from app.models import Chapter

def now():return datetime.now(timezone.utc)
async def enqueue(db,kind,payload,delay_hours=0):
    import json
    key=hashlib.sha256(json.dumps([kind,payload],sort_keys=True).encode()).hexdigest()
    await db.execute(insert(CleanupTask).values(id=str(uuid4()),operation_key=key,kind=kind,payload=payload,status='queued',attempts=0,due_at=now()+timedelta(hours=delay_hours)).on_conflict_do_update(index_elements=['operation_key'],set_={'status':'queued','due_at':now()+timedelta(hours=delay_hours),'attempts':0},where=CleanupTask.status=='retained'))
async def prepare_project(db,book):
    rows=(await db.execute(select(SourceBlob).join(StorySource,StorySource.id==SourceBlob.source_id).where(StorySource.book_id==book.id))).scalars()
    for row in rows:await enqueue(db,'blob',{'key':row.object_key},24)
    for row in await db.scalars(select(StorySource).where(StorySource.book_id==book.id)):
        for idx in await db.scalars(select(SourceIndex).join(SourceChapter,SourceChapter.id==SourceIndex.source_chapter_id).where(SourceChapter.source_id==row.id)):
            await enqueue(db,'index',{'user_id':book.user_id,'namespace':'source_'+row.id.replace('-',''),'physical_id':idx.physical_id},24)
    for chapter in await db.scalars(select(Chapter).where(Chapter.book_id==book.id)):
        await enqueue(db,'index',{'user_id':book.user_id,'namespace':book.id,'physical_id':chapter.id},24)
    for row in await db.scalars(select(IndexManifest).join(Chapter,Chapter.id==IndexManifest.chapter_id).where(Chapter.book_id==book.id)):
        await enqueue(db,'index',{'user_id':book.user_id,'namespace':book.id,'physical_id':row.physical_id},24)
async def prepare_chapter(db,chapter):
    book=await db.get(Book,chapter.book_id)
    await enqueue(db,'index',{'user_id':book.user_id,'namespace':book.id,'physical_id':chapter.id},24)
    for row in await db.scalars(select(IndexManifest).where(IndexManifest.chapter_id==chapter.id)):
        await enqueue(db,'index',{'user_id':book.user_id,'namespace':book.id,'physical_id':row.physical_id},24)
async def discover_retired():
    async with AsyncSessionLocal() as db:
        rows=(await db.execute(select(IndexManifest,Book).join(Chapter,Chapter.id==IndexManifest.chapter_id).join(Book,Book.id==Chapter.book_id).where(IndexManifest.status.in_(['retired','failed','staging']),IndexManifest.created_at<now()-timedelta(hours=24)).limit(100))).all()
        for row,book in rows:
            await enqueue(db,'index',{'user_id':book.user_id,'namespace':book.id,'physical_id':row.physical_id})
        await db.commit()
async def poll_once():
    async with AsyncSessionLocal() as db:
        task=await db.scalar(select(CleanupTask).where(CleanupTask.status.in_(['queued','running']),CleanupTask.due_at<=now()).order_by(CleanupTask.due_at).with_for_update(skip_locked=True).limit(1))
        if not task:return False
        task.status='running';task.attempts+=1;task.due_at=now()+timedelta(minutes=5);tid=task.id;kind=task.kind;p=task.payload;await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            if kind=='blob':
                if await db.scalar(select(SourceBlob.source_id).where(SourceBlob.object_key==p['key'])):status='retained'
                else:
                    from app.services.storage.blob_store import store
                    await store().delete(p['key']);status='succeeded'
            elif kind=='index':
                # Recheck authority immediately before physical deletion, even for manual retries.
                active=await db.scalar(select(IndexManifest.id).where(IndexManifest.physical_id==p['physical_id'],IndexManifest.status=='active'))
                active_source=await db.scalar(select(SourceIndex.id).where(SourceIndex.physical_id==p['physical_id'],SourceIndex.status=='active'))
                if active or active_source:status='retained'
                else:
                    from storyclaw.rag.service import delete_generation
                    await delete_generation(p['user_id'],p['namespace'],p['physical_id']);status='succeeded'
            else:raise ValueError('Unknown cleanup kind')
        async with AsyncSessionLocal() as db:
            task=await db.get(CleanupTask,tid);task.status=status;task.error=None
            if kind=='index' and status=='succeeded':
                await db.execute(update(IndexManifest).where(IndexManifest.physical_id==p['physical_id'],IndexManifest.status!='active').values(status='cleaned'))
                await db.execute(update(SourceIndex).where(SourceIndex.physical_id==p['physical_id'],SourceIndex.status!='active').values(status='cleaned'))
            await db.commit()
    except Exception:
        logging.getLogger(__name__).exception('Cleanup failed id=%s',tid)
        async with AsyncSessionLocal() as db:
            task=await db.get(CleanupTask,tid);task.status='failed' if task.attempts>=8 else 'queued';task.error='物理清理失败，请检查存储连接后重试';task.due_at=now()+timedelta(minutes=min(1440,2**task.attempts));await db.commit()
    return True
async def queue_loop():
    tick=0
    while True:
        try:
            if tick%30==0:await discover_retired()
            await poll_once();tick+=1
        except asyncio.CancelledError:raise
        except Exception:logging.getLogger(__name__).exception('Cleanup discovery failed')
        await asyncio.sleep(10)
