"""Delete a project dependency tree without following ownership links to users/posts."""
from fastapi import HTTPException
from sqlalchemy import select,delete,or_
from ..models import Base,Book,Chapter
from ..models.studio import StorySource,ProjectBaseline,ImportedChapter,StudioTask
from ..models.agent import AgentRun
async def delete_project(db,book):
    source_ids=select(StorySource.id).where(StorySource.book_id==book.id)
    if await db.scalar(select(ProjectBaseline.book_id).where(ProjectBaseline.source_id.in_(source_ids),ProjectBaseline.book_id!=book.id).limit(1)):
        raise HTTPException(409,'此作品的原作来源被其他分支使用，请先在分支解除或更换来源')
    if await db.scalar(select(ImportedChapter.chapter_id).join(Chapter,Chapter.id==ImportedChapter.chapter_id).where(ImportedChapter.source_id.in_(source_ids),Chapter.book_id!=book.id).limit(1)):
        raise HTTPException(409,'此来源仍被另一部接管作品使用，请保留来源工程')
    if await db.scalar(select(StudioTask.id).where(or_(StudioTask.book_id==book.id,StudioTask.payload['source_id'].as_string().in_(source_ids)),StudioTask.status.in_(['queued','running'])).limit(1)):
        raise HTTPException(409,'请先暂停长期计划，再删除作品')
    if await db.scalar(select(AgentRun.id).where(AgentRun.user_id==book.user_id,AgentRun.request['scope']['book_id'].as_integer()==book.id,AgentRun.status.in_(['accepted','running','waiting_task'])).limit(1)):
        raise HTTPException(409,'请先完成或取消本书的创作请求')
    from .cleanup import prepare_project
    await prepare_project(db,book)
    # Build descendants in dependency order. Do not walk to parents (users, community posts).
    scopes={'books':Book.__table__.c.id==book.id}
    tables=list(Base.metadata.sorted_tables)
    for table in tables:
        if table.name=='books':continue
        conditions=[]
        for fk in table.foreign_keys:
            parent=fk.column.table
            if parent.name in scopes:
                conditions.append(fk.parent.in_(select(fk.column).where(scopes[parent.name])))
        if conditions:scopes[table.name]=or_(*conditions)
    from ..models import EntityKv,ConfigEntity
    await db.execute(delete(EntityKv).where(EntityKv.entity_id.in_(select(ConfigEntity.id).where(ConfigEntity.book_id==book.id))))
    for table in reversed(tables):
        if table.name in scopes and table.name!='books':await db.execute(delete(table).where(scopes[table.name]))
    await db.execute(delete(Book).where(Book.id==book.id))
