"""Incremental history dependency chain. Editing N invalidates cached suffixes from N."""
import hashlib,json
from sqlalchemy import select,text
from sqlalchemy.dialects.postgresql import insert
from ..models.operations import HistoryPrefix
from ..models.studio import ChapterFingerprint,IndexManifest
async def history_digest(db,bid,upto):
    if upto<=0:return hashlib.sha256(b'storyclaw-history-v1').hexdigest()
    await db.execute(text('SELECT pg_advisory_xact_lock(CAST(:key AS BIGINT))'),{'key':916000000000+bid})
    # Old databases bootstrap only fingerprints not previously materialized.
    await db.execute(text("INSERT INTO chapter_fingerprints(chapter_id,book_id,number,body_hash) SELECT id,book_id,number,md5(title || E'\\n' || content) FROM chapters WHERE book_id=:bid AND number<=:upto AND NOT EXISTS(SELECT 1 FROM chapter_fingerprints f WHERE f.chapter_id=chapters.id) ON CONFLICT(chapter_id) DO NOTHING"),{'bid':bid,'upto':upto})
    cached=await db.scalar(select(HistoryPrefix.digest).where(HistoryPrefix.book_id==bid,HistoryPrefix.upto==upto))
    if cached is not None:return cached
    prior=(await db.execute(select(HistoryPrefix.upto,HistoryPrefix.digest).where(HistoryPrefix.book_id==bid,HistoryPrefix.upto<upto).order_by(HistoryPrefix.upto.desc()).limit(1))).first()
    start=prior.upto if prior else 0;root=prior.digest if prior else hashlib.sha256(b'storyclaw-history-v1').hexdigest()
    changes=(await db.execute(select(ChapterFingerprint.chapter_id,ChapterFingerprint.number,ChapterFingerprint.body_hash,IndexManifest.id).outerjoin(IndexManifest,(IndexManifest.chapter_id==ChapterFingerprint.chapter_id)&(IndexManifest.status=='active')).where(ChapterFingerprint.book_id==bid,ChapterFingerprint.number>start,ChapterFingerprint.number<=upto).order_by(ChapterFingerprint.number,ChapterFingerprint.chapter_id))).all()
    for cid,number,digest,generation in changes:root=hashlib.sha256(json.dumps([root,cid,number,digest,generation],separators=(',',':')).encode()).hexdigest()
    await db.execute(insert(HistoryPrefix).values(book_id=bid,upto=upto,digest=root).on_conflict_do_nothing())
    return root
