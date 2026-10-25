"""Scoped source repositories, author-approved takeover and branch context."""
import hashlib,json,re,zipfile
from xml.etree.ElementTree import ParseError
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,func,insert
from storyclaw.workflows.library import decode_manuscript,split_manuscript
from ..models import Book,Chapter,Outline
from ..models.studio import StorySource,SourceChapter,ProjectBaseline,ImportedChapter

async def own_book(db,uid,bid,lock=False):
    q=select(Book).where(Book.id==bid,Book.user_id==uid)
    book=await db.scalar(q.with_for_update() if lock else q)
    if not book:raise HTTPException(404,'作品不存在')
    return book

async def own_source(db,uid,sid):
    row=await db.scalar(select(StorySource).where(StorySource.id==sid,StorySource.user_id==uid))
    if not row:raise HTTPException(404,'来源不存在')
    return row

async def upload(db,uid,bid,filename,data,rights):
    await own_book(db,uid,bid,True)
    if not rights.get('read_allowed'):raise HTTPException(400,'请确认有权将该资料上传供本账号使用')
    digest=hashlib.sha256(data).hexdigest()
    prior=await db.scalar(select(StorySource).where(StorySource.user_id==uid,StorySource.book_id==bid,StorySource.file_hash==digest))
    if prior:return prior
    try:text=decode_manuscript(filename,data);parts,warnings=split_manuscript(text)
    except (ValueError,KeyError,zipfile.BadZipFile,ParseError) as exc:raise HTTPException(422,str(exc)) from exc
    if not parts:raise HTTPException(422,'文件没有可用正文，请核对文件内容')
    source=StorySource(id=str(uuid4()),user_id=uid,book_id=bid,title=filename[:255],filename=filename[:255],original=data,file_hash=digest,rights=rights,status='imported',warnings=warnings)
    db.add(source);await db.flush()
    for start in range(0,len(parts),100):
        await db.execute(insert(SourceChapter),[{'source_id':source.id,'number':p['number'],'title':p['title'][:255],'content':p['content'],'content_hash':p['hash'],'words':p['words'],'analysis_status':'pending'} for p in parts[start:start+100]])
    from .blob_store import write_original
    await write_original(db,source,data)
    await db.commit();return source

async def coverage(db,source):
    rows=(await db.execute(select(SourceChapter.analysis_status,func.count(),func.sum(SourceChapter.words)).where(SourceChapter.source_id==source.id).group_by(SourceChapter.analysis_status))).all()
    return {'id':source.id,'title':source.title,'filename':source.filename,'file_hash':source.file_hash,'status':source.status,'rights':source.rights,'warnings':source.warnings,
        'chapters':sum(r[1] for r in rows),'words':sum(r[2] or 0 for r in rows),'coverage':{r[0]:r[1] for r in rows}}

async def baseline_confirm(db,uid,bid,data):
    book=await own_book(db,uid,bid,True);source=await own_source(db,uid,data['source_id'])
    if source.status=='revoked':raise HTTPException(409,'该来源已停用')
    if not source.rights.get('read_allowed'):raise HTTPException(409,'来源使用许可已撤销')
    # A source may be reused across this author's projects; never across authors.
    if data['file_hash']!=source.file_hash:raise HTTPException(409,'来源版本已变化')
    count=await db.scalar(select(func.count()).select_from(SourceChapter).where(SourceChapter.source_id==source.id))
    if not 1<=data['cutoff']<=count:raise HTTPException(422,'接续范围不在来源章节内')
    existing=await db.get(ProjectBaseline,bid)
    if existing and (existing.mode!=data['mode'] or (existing.mode=='takeover' and existing.cutoff!=data['cutoff'])):raise HTTPException(409,'接管模式或历史范围变化请新建空白分支；不会自动移动或覆盖既有正文')
    if data['mode']=='takeover' and source.rights.get('basis')!='own':raise HTTPException(422,'接管原作正文仅限本人采用稿；他人原作用独立衍生分支')
    if data['mode']=='takeover' and not existing:
        if await db.scalar(select(Chapter.id).where(Chapter.book_id==bid).limit(1)):raise HTTPException(409,'接管请使用空白作品，避免覆盖现有正文')
        # Batch copy only author-approved original text, no AI changes or fake loaded status.
        offset=0
        while True:
            parts=list(await db.scalars(select(SourceChapter).where(SourceChapter.source_id==source.id,SourceChapter.number<=data['cutoff']).order_by(SourceChapter.number).offset(offset).limit(100)))
            if not parts:break
            for part in parts:
                chapter=Chapter(book_id=bid,number=part.number,title=part.title,content=part.content,word_count=part.words,rag_status='pending')
                db.add(chapter);await db.flush();db.add(ImportedChapter(chapter_id=chapter.id,source_chapter_id=part.id,source_id=source.id))
            offset+=len(parts)
    elif existing and existing.source_id!=source.id:raise HTTPException(409,'升级原作版本请新建分支并预览，不会覆盖当前基线')
    pending=await db.scalar(select(func.count()).select_from(SourceChapter).where(SourceChapter.source_id==source.id,SourceChapter.number<=data['cutoff'],SourceChapter.analysis_status!='ready'))
    from storyclaw.serial import digest
    config={k:data[k] for k in ('source_id','mode','cutoff','notes','overrides','branch_kind','file_hash')}
    if existing and existing.confirmed_hash==digest(config) and existing.status!='stale':return existing
    if not existing:
        existing=ProjectBaseline(book_id=bid,source_id=source.id,mode=data['mode'],status='assisted_ready',cutoff=data['cutoff'],notes=data['notes'],overrides=data['overrides'],branch_kind=data['branch_kind'],version=0,confirmed_hash='')
        db.add(existing)
    else:
        from .serial import invalidate_book
        await invalidate_book(db,bid,'接管基线/分支规则已变化，请核对已有正文')
    existing.mode=data['mode'];existing.cutoff=data['cutoff'];existing.notes=data['notes'];existing.overrides=data['overrides'];existing.branch_kind=data['branch_kind']
    existing.version+=1;existing.confirmed_hash=digest(config);existing.status='baseline_ready' if not pending else 'assisted_ready'
    if data['mode']=='takeover':book.target_words=(await db.scalar(select(func.sum(Chapter.word_count)).where(Chapter.book_id==bid)) or 0)+data.get('additional_words',3000000)
    await db.commit();return existing

async def imported_exemptions(db,bid):
    baseline=await db.get(ProjectBaseline,bid)
    if not baseline or baseline.mode!='takeover' or baseline.status not in ('assisted_ready','baseline_ready'):return set()
    source=await db.get(StorySource,baseline.source_id)
    if not source or source.status=='revoked' or not source.rights.get('read_allowed'):return set()
    return set(await db.scalars(select(ImportedChapter.chapter_id).join(Chapter,Chapter.id==ImportedChapter.chapter_id).where(Chapter.book_id==bid,ImportedChapter.source_id==baseline.source_id,Chapter.number<=baseline.cutoff)))

async def invalidate_import(db,chapter):
    origin=await db.get(ImportedChapter,chapter.id)
    if origin:
        baseline=await db.get(ProjectBaseline,chapter.book_id)
        if baseline:baseline.status='stale';baseline.version+=1
        await db.delete(origin)

async def reference_context(db,uid,bid,query=''):
    baseline=await db.get(ProjectBaseline,bid)
    if not baseline:return {}
    source=await own_source(db,uid,baseline.source_id)
    if source.status=='revoked' or baseline.status=='stale':raise HTTPException(409,'来源/接管基线已失效，请先核对后重新确认')
    if not source.rights.get('ai_allowed'):raise HTTPException(409,'此来源未允许发送给模型；可人工阅读，不能自动续写')
    # Cutoff is the branch knowledge boundary, never inferred from original work's ending.
    q=select(SourceChapter).where(SourceChapter.source_id==source.id,SourceChapter.number<=baseline.cutoff)
    if baseline.mode=='takeover':
        valid=select(SourceChapter.number).join(ImportedChapter,ImportedChapter.source_chapter_id==SourceChapter.id).join(Chapter,Chapter.id==ImportedChapter.chapter_id).where(Chapter.book_id==bid,ImportedChapter.source_id==source.id)
        q=q.where(SourceChapter.number.in_(valid))
    tokens=list(dict.fromkeys(re.findall(r'[\u4e00-\u9fff]{2,8}|[A-Za-z]{3,}',query)))[:4]
    parts=[]
    if tokens:
        from sqlalchemy import or_
        parts=list(await db.scalars(q.where(or_(*[SourceChapter.content.contains(t,autoescape=True) for t in tokens])).order_by(SourceChapter.number.desc()).limit(4)))
    if not parts:parts=list(await db.scalars(q.order_by(SourceChapter.number.desc()).limit(3)))
    from ..models.studio import SourceIndex
    iq=select(SourceIndex.physical_id,SourceChapter.number).join(SourceChapter,SourceChapter.id==SourceIndex.source_chapter_id).where(SourceChapter.source_id==source.id,SourceChapter.number<=baseline.cutoff,SourceIndex.status=='active')
    if baseline.mode=='takeover':iq=iq.where(SourceChapter.number.in_(valid))
    active=list((await db.execute(iq)).all())
    semantic={}
    if active and query:
        from storyclaw.rag.service import query_context
        mapping=dict(active)
        semantic=await query_context(uid,'source_'+source.id.replace('-',''),query[:1000],4,list(mapping),resolve_manifest=False)
        semantic={**semantic,'chunks':[{**c,'source_chapter':mapping.get(c.get('chapter_id'))} for c in semantic.get('chunks',[])]}
    return {'mode':baseline.mode,'branch_kind':baseline.branch_kind,'source_id':source.id,'source_version':source.file_hash,'baseline_version':baseline.version,'coverage':baseline.status,
        'semantic_evidence':semantic,'author_baseline':baseline.notes,'branch_overrides':baseline.overrides,'cutoff':baseline.cutoff,
        'evidence':[{'source_chapter':p.number,'title':p.title,'summary':(p.analysis or {}).get('summary'),
            'text':p.content[-2500:],'status':p.analysis_status} for p in parts],
        'warning':'来源是只读参考。分歧之后的原作事件不自动成立；只保留明确继承事实，角色不自动知道作者知道的秘密。' if baseline.mode=='derivative' else '导入原文已获作者采用；未深度分析的部分仅代表可查资料，不代表AI已经读完全书。'}
