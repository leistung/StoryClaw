"""Bounded durable summaries and evidence, always tied to active manuscript generations."""
from sqlalchemy import select,or_
from ..models import Chapter
from ..models.studio import IndexManifest
async def memory_context(db,bid,number,query=''):
    q=select(IndexManifest,Chapter.number).join(Chapter,Chapter.id==IndexManifest.chapter_id).where(Chapter.book_id==bid,Chapter.number<number,Chapter.rag_status=='loaded',IndexManifest.status=='active')
    recent=(await db.execute(q.order_by(Chapter.number.desc()).limit(4))).all()
    import re
    words=list(dict.fromkeys(re.findall(r'[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,}',query)))[:3]
    matches=[]
    if words:
        matches=(await db.execute(q.where(or_(*[IndexManifest.result['memory'].as_string().contains(w,autoescape=True) for w in words])).order_by(Chapter.number.desc()).limit(4))).all()
    evidence={r.chapter_id:(r,n) for r,n in [*recent,*matches]}
    return [{'chapter_id':r.chapter_id,'number':n,'body_hash':r.body_hash,'summary':r.result.get('memory',{}).get('summary','')[:1800],
             'facts':r.result.get('memory',{}).get('facts',[])[:15],'unresolved':r.result.get('memory',{}).get('unresolved',[])[:10]} for r,n in evidence.values()]
