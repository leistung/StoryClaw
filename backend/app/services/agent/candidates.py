"""候选采用事务：归属、版本和任务锁校验后才写入；HTTP 层只传入作者决定。"""
from fastapi import HTTPException

async def adopt_candidate(rid, expected_hash, user, db):
    from app.services.agent.agent_decisions import owned
    from app.models import Chapter
    from app.models import Book
    from app.services.writing.revisions import assert_editable
    from app.services.writing.revisions import chapter_hash
    from app.services.writing.revisions import snapshot
    from storyclaw.workflows.continuity import prose
    from app.services.writing.content import reading_html
    from sqlalchemy import select
    row = await owned(rid, user, db, True)
    result = row.result or {}
    artifact = result.get('data') or {}
    if row.status != 'succeeded' or not artifact.get('artifact') or artifact.get('adopted'):
        raise HTTPException(409, '候选不可采用或已经采用')
    kind = artifact.get('kind', '')
    # 设定与正文分别校验生成时的版本；模型候选不可覆盖作者之后的手动修改。
    if kind == 'setting.update':
        from app.models import ConfigEntity
        from app.services.agent.setting_edits import setting_hash
        from app.services.writing.serial import assert_book_idle, invalidate_book
        bid = row.request['scope']['book_id']
        book = await db.scalar(select(Book).where(Book.id == bid, Book.user_id == user.id).with_for_update())
        if not book:
            raise HTTPException(404, '作品不存在')
        await assert_book_idle(db, bid)
        entity = await db.scalar(select(ConfigEntity).where(ConfigEntity.id == artifact['entity_id'], ConfigEntity.book_id == bid).with_for_update())
        if not entity:
            raise HTTPException(404, '设定不存在')
        if setting_hash(entity) != expected_hash or artifact['base_hash'] != expected_hash:
            raise HTTPException(409, '设定已变化，请重新生成修改候选')
        after = artifact['setting_change']['after']
        duplicate = await db.scalar(select(ConfigEntity.id).where(ConfigEntity.book_id == bid, ConfigEntity.entity_type == entity.entity_type, ConfigEntity.name == after['name'], ConfigEntity.id != entity.id))
        if duplicate:
            raise HTTPException(409, '修改后的档案名已存在，请调整名称')
        for field in ('name', 'category', 'description'):
            setattr(entity, field, after[field])
        await invalidate_book(db, bid, '已采用对话助手的设定修改，请复核既有正文和章纲')
        row.result = {**result, 'data': {**artifact, 'adopted': True, 'adopted_hash': setting_hash(entity)}}
        await db.commit()
        return {'entity_id': entity.id, 'adopted': True}
    if not kind.startswith('text.'):
        raise HTTPException(422, '此候选请在对应资料编辑页手动选择采用')
    cid = artifact.get('chapter_id')
    chapter = await db.get(Chapter, cid) if cid else None
    if not chapter:
        raise HTTPException(404, '章节不存在')
    book = await db.scalar(select(Book).where(Book.id == chapter.book_id, Book.user_id == user.id).with_for_update())
    if not book:
        raise HTTPException(404, '章节不存在')
    await db.refresh(chapter)
    await assert_editable(db, cid)
    if chapter_hash(chapter) != expected_hash or artifact.get('base_hash') != expected_hash:
        raise HTTPException(409, '正文已修改，请重新生成或手动对照采用')
    old = prose(chapter.content)
    candidate = result.get('content', '').strip()
    selected = artifact.get('selected_text', '')
    if not candidate:
        raise HTTPException(422, '候选正文为空')
    span = artifact.get('range')
    if span:
        start, end = (span['start'], span['end'])
        if start < 0 or end < start or end > len(old) or (old[start:end] != span['text']):
            raise HTTPException(409, '原引用位置已失效，请重新生成')
        from app.services.agent.manuscript_references import replace_range
        try:
            html = replace_range(chapter.content, start, end, candidate, span.get('affinity', 'before'))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        new = prose(html)
    elif kind == 'text.continue':
        new = old + '\n\n' + candidate
    else:
        if not selected or old.count(selected) != 1:
            raise HTTPException(409, '原片段不存在或有重复，请在编辑器中手动采用')
        new = old.replace(selected, candidate, 1)
    # 旧版本、正文和采用状态在同一事务提交，避免候选已标记采用而正文未保存。
    await snapshot(db, chapter, 'agent-candidate')
    chapter.content = html if span else reading_html(new)
    chapter.word_count = len(''.join(new.split()))
    chapter.rag_status = 'pending'
    row.result = {**result, 'data': {**artifact, 'adopted': True, 'adopted_hash': chapter_hash(chapter)}}
    await db.commit()
    return {'chapter_id': cid, 'content_hash': chapter_hash(chapter), 'adopted': True}
