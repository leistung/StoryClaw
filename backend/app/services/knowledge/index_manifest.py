"""Publish only complete matching vector+graph generations to retrieval."""
from secrets import randbits
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Book
from app.models import Chapter
from app.models.studio import IndexManifest
async def stage(db,chapter,body_hash):
    # Physical IDs stay within signed int64 even after chunk_idx encoding (x10000).
    row=IndexManifest(chapter_id=chapter.id,body_hash=body_hash,physical_id=-(randbits(46)+1),status='staging',result={})
    db.add(row);await db.commit();return row
async def activate(db,row,chapter,result,body_hash):
    from app.services.writing.revisions import chapter_hash
    from sqlalchemy import text
    await db.execute(text('SELECT pg_advisory_xact_lock(CAST(:key AS BIGINT))'),{'key':916000000000+chapter.book_id})
    await db.refresh(chapter)
    okay=chapter_hash(chapter)==body_hash and result.get('chunks',0)>0 and not result.get('error') and result.get('stores',{}).get('vector')=='milvus' and result.get('stores',{}).get('graph')=='neo4j'
    if okay:
        old=list(await db.scalars(select(IndexManifest).where(IndexManifest.chapter_id==chapter.id,IndexManifest.status=='active')))
        for prior in old:prior.status='retired'
    row.status='active' if okay else 'failed';row.result=result
    if okay:
        from app.services.knowledge.narrative_state import activate_facts
        await activate_facts(db,row,chapter)
        from sqlalchemy import delete
        from app.models.operations import HistoryPrefix
        await db.execute(delete(HistoryPrefix).where(HistoryPrefix.book_id==chapter.book_id,HistoryPrefix.upto>=chapter.number))
    return okay
async def resolve(uid,bid,allowed=None):
    async with AsyncSessionLocal() as db:
        q=select(Chapter.id).join(Book,Book.id==Chapter.book_id).where(Book.user_id==uid,Book.id==bid,Chapter.rag_status=='loaded')
        if allowed is not None:q=q.where(Chapter.id.in_(allowed))
        ids=list(await db.scalars(q))
        active=list(await db.scalars(select(IndexManifest).where(IndexManifest.chapter_id.in_(ids),IndexManifest.status=='active')))
        mapped={r.chapter_id:r.physical_id for r in active}
        # Legacy indexes remain readable until a generation is activated. Failed staging is never visible.
        return {mapped.get(cid,cid):cid for cid in ids}
