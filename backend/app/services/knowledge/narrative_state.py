"""Versioned host persistence for source-bound facts and author knowledge decisions."""
from uuid import uuid4,uuid5,NAMESPACE_URL
from sqlalchemy import select,or_
from app.models.operations import NarrativeFact
from app.models.operations import NarrativeEntity
from app.models.operations import NarrativePolicy
from app.models.operations import NarrativeFocus
from app.models.studio import IndexManifest
from app.models import Chapter
from app.services.writing.revisions import chapter_hash
async def activate_facts(db,manifest,chapter):
    from storyclaw.workflows.continuity import prose
    source=prose(chapter.content)
    for i,fact in enumerate(manifest.result.get('memory',{}).get('facts',[])):
        if not fact.get('quote') or fact['quote'] not in source:raise ValueError('摘要事实没有对应原文证据，不能激活')
        fid=str(uuid5(NAMESPACE_URL,f'fact:{manifest.id}:{i}'))
        if await db.get(NarrativeFact,fid):continue
        db.add(NarrativeFact(id=fid,book_id=chapter.book_id,chapter_id=chapter.id,manifest_id=manifest.id,body_hash=manifest.body_hash,
            subject=fact['subject'][:120],statement=fact['statement'],quote=fact['quote'],kind=fact['kind'],certainty=fact.get('certainty','claim'),holder=fact.get('holder','')[:120],
            known_by=fact.get('known_by',[])[:30],public=False,story_time=fact.get('story_time','')[:200],causes=[],valid_from=chapter.number,review_status='suggested'))
async def bump(db,bid):
    from sqlalchemy.dialects.postgresql import insert
    await db.execute(insert(NarrativePolicy).values(book_id=bid,version=1).on_conflict_do_update(index_elements=['book_id'],set_={'version':NarrativePolicy.version+1}))
def out(r):
    return {k:getattr(r,k) for k in ('id','chapter_id','body_hash','subject','statement','quote','kind','certainty','holder','known_by','public','story_time','causes','valid_from','valid_until','review_status','version')}
async def view(db,bid,number,persona='',limit=200):
    from storyclaw.knowledge import knowledge_view
    # Only active matching sources enter generation; obsolete candidates remain visible in review API.
    q=select(NarrativeFact).join(Chapter,Chapter.id==NarrativeFact.chapter_id).join(IndexManifest,IndexManifest.id==NarrativeFact.manifest_id).where(NarrativeFact.book_id==bid,NarrativeFact.valid_from<number,Chapter.rag_status=='loaded',IndexManifest.status=='active').order_by(NarrativeFact.valid_from.desc()).limit(limit)
    facts=[]
    for r in await db.scalars(q):
        facts.append(out(r))
    entities=[{'name':r.name,'aliases':r.aliases} for r in await db.scalars(select(NarrativeEntity).where(NarrativeEntity.book_id==bid))]
    return knowledge_view(facts,chapter_number=number,persona=persona,entities=entities)
