"""Author-approved scheduled delivery to this platform; external delivery stays manual."""
import asyncio,logging
from datetime import datetime,timezone
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.operations import ReleaseDelivery
from app.models.studio import ReleaseRecord
from app.models.studio import ProjectBaseline
from app.models.studio import StorySource
from app.models.product import Publication
from app.models import Book
from app.models.platform import PlatformEvent
from app.services.writing.content import reading_html
async def deliver(db,record):
    b=await db.get(Book,record.book_id)
    if not b or b.user_id!=record.user_id:raise ValueError('作品已删除或无权发布')
    baseline=await db.get(ProjectBaseline,b.id)
    if baseline:
        source=await db.get(StorySource,baseline.source_id)
        if not source or source.status=='revoked' or baseline.status=='stale':raise ValueError('来源或接管基线已失效，请重新核对')
        if not source.rights.get('read_allowed'):raise ValueError('来源用途未确认')
    snap={**record.snapshot,'id':b.id,'cover_url':b.cover_url or ''}
    snap['chapters']=[{**c,'content':reading_html(c['content']),'word_count':len(''.join(c['content'].split()))} for c in snap['chapters']]
    pub=await db.get(Publication,b.id)
    if not pub:pub=Publication(book_id=b.id,user_id=b.user_id,snapshot=snap);db.add(pub)
    pub.snapshot=snap;pub.visible=True;pub.published_at=datetime.now(timezone.utc)
    record.receipt={**record.receipt,'delivery':{'source':'storyclaw','snapshot_hash':record.snapshot['hash'],'url':f'/read/{b.id}'}};record.status='published'
    db.add(PlatformEvent(kind='audit',actor_id=b.user_id,action='release.deliver',target=record.id,details={'hash':record.snapshot['hash']}))
async def poll_once():
    async with AsyncSessionLocal() as db:
        candidate=await db.scalar(select(ReleaseDelivery.release_id).where(ReleaseDelivery.status=='scheduled',ReleaseDelivery.due_at<=datetime.now(timezone.utc)).order_by(ReleaseDelivery.due_at).limit(1))
        if not candidate:return False
        record=await db.get(ReleaseRecord,candidate)
        if not record:return False
        book=await db.scalar(select(Book).where(Book.id==record.book_id).with_for_update(skip_locked=True))
        if not book:return False
        row=await db.scalar(select(ReleaseDelivery).where(ReleaseDelivery.release_id==candidate,ReleaseDelivery.status=='scheduled',ReleaseDelivery.due_at<=datetime.now(timezone.utc)).with_for_update(skip_locked=True))
        if not row:return False
        record=await db.get(ReleaseRecord,row.release_id)
        try:
            if not record:raise ValueError('投稿记录不存在')
            # Publish and mark delivered in the same transaction: restart cannot double-deliver.
            await deliver(db,record);row.status='delivered';row.delivered_at=datetime.now(timezone.utc);row.error=None
        except ValueError as exc:row.status='blocked';row.error=str(exc)
        await db.commit();return True
async def queue_loop():
    while True:
        try:await poll_once()
        except asyncio.CancelledError:raise
        except Exception:logging.getLogger(__name__).exception('Release delivery failed')
        await asyncio.sleep(3)
