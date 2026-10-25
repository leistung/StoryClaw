"""Long-form source provenance, baselines, branches, plans and publishing records."""
from datetime import datetime
from sqlalchemy import DateTime,ForeignKey,JSON,String,Text,Integer,LargeBinary,UniqueConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from app.models.base import Base

class StorySource(Base):
    __tablename__='story_sources'
    __table_args__=(UniqueConstraint('user_id','book_id','file_hash',name='uq_story_source_file'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),index=True)
    title:Mapped[str]=mapped_column(String(255))
    filename:Mapped[str]=mapped_column(String(255))
    original:Mapped[bytes]=mapped_column(LargeBinary)
    file_hash:Mapped[str]=mapped_column(String(64))
    rights:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(24),default='imported')
    warnings:Mapped[list]=mapped_column(JSON,default=list)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class SourceChapter(Base):
    __tablename__='source_chapters'
    __table_args__=(UniqueConstraint('source_id','number',name='uq_source_chapter_number'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    source_id:Mapped[str]=mapped_column(ForeignKey('story_sources.id',ondelete='CASCADE'),index=True)
    number:Mapped[int]=mapped_column(Integer)
    title:Mapped[str]=mapped_column(String(255))
    content:Mapped[str]=mapped_column(Text)
    content_hash:Mapped[str]=mapped_column(String(64))
    words:Mapped[int]=mapped_column(Integer)
    analysis:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    analysis_status:Mapped[str]=mapped_column(String(24),default='pending')
    error:Mapped[str|None]=mapped_column(Text,nullable=True)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class ProjectBaseline(Base):
    __tablename__='project_baselines'
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),primary_key=True)
    source_id:Mapped[str]=mapped_column(ForeignKey('story_sources.id'),index=True)
    mode:Mapped[str]=mapped_column(String(24))
    status:Mapped[str]=mapped_column(String(24),default='imported')
    cutoff:Mapped[int]=mapped_column(Integer)
    notes:Mapped[str]=mapped_column(Text)
    overrides:Mapped[str]=mapped_column(Text,default='')
    branch_kind:Mapped[str]=mapped_column(String(24),default='continuation')
    version:Mapped[int]=mapped_column(Integer,default=1)
    confirmed_hash:Mapped[str]=mapped_column(String(64))

class ImportedChapter(Base):
    __tablename__='imported_chapters'
    chapter_id:Mapped[int]=mapped_column(ForeignKey('chapters.id',ondelete='CASCADE'),primary_key=True)
    source_chapter_id:Mapped[int]=mapped_column(ForeignKey('source_chapters.id'),index=True)
    source_id:Mapped[str]=mapped_column(ForeignKey('story_sources.id'),index=True)

class StudioTask(Base):
    __tablename__='studio_tasks'
    __table_args__=(UniqueConstraint('user_id','request_id',name='uq_studio_task_request'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),index=True)
    request_id:Mapped[str]=mapped_column(String(64))
    kind:Mapped[str]=mapped_column(String(24))
    status:Mapped[str]=mapped_column(String(24),default='queued',index=True)
    payload:Mapped[dict]=mapped_column(JSON)
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    error:Mapped[str|None]=mapped_column(Text,nullable=True)
    budget:Mapped[int]=mapped_column(Integer)
    spent:Mapped[int]=mapped_column(Integer,default=0)
    current_job:Mapped[str|None]=mapped_column(String(36),nullable=True)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class ReleaseRecord(Base):
    __tablename__='release_records'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),index=True)
    platform:Mapped[str]=mapped_column(String(100))
    status:Mapped[str]=mapped_column(String(24),default='prepared')
    snapshot:Mapped[dict]=mapped_column(JSON)
    policy:Mapped[dict]=mapped_column(JSON)
    receipt:Mapped[dict]=mapped_column(JSON,default=dict)
    scheduled_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class PrivateMethod(Base):
    __tablename__='private_methods'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    title:Mapped[str]=mapped_column(String(150))
    content:Mapped[str]=mapped_column(Text)
    enabled:Mapped[bool]=mapped_column(default=False)

class ModelCall(Base):
    __tablename__='model_calls'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    job_id:Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    plan_id:Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    model:Mapped[str]=mapped_column(String(150))
    status:Mapped[str]=mapped_column(String(24),default='reserved')
    reserved:Mapped[int]=mapped_column(Integer)
    cost:Mapped[int]=mapped_column(Integer,default=0)
    usage:Mapped[dict]=mapped_column(JSON,default=dict)
    lease_until:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class IndexManifest(Base):
    __tablename__='index_manifests'
    id:Mapped[int]=mapped_column(primary_key=True)
    chapter_id:Mapped[int]=mapped_column(ForeignKey('chapters.id',ondelete='CASCADE'),index=True)
    body_hash:Mapped[str]=mapped_column(String(64))
    physical_id:Mapped[int]=mapped_column(__import__('sqlalchemy').BigInteger,unique=True)
    status:Mapped[str]=mapped_column(String(24),default='staging')
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class ChapterFingerprint(Base):
    __tablename__='chapter_fingerprints'
    chapter_id:Mapped[int]=mapped_column(ForeignKey('chapters.id',ondelete='CASCADE'),primary_key=True)
    book_id:Mapped[int]=mapped_column(Integer,index=True)
    number:Mapped[int]=mapped_column(Integer)
    body_hash:Mapped[str]=mapped_column(String(64))

from sqlalchemy import event,DDL
FINGERPRINT_FUNCTION="""
CREATE OR REPLACE FUNCTION storyclaw_chapter_fingerprint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO chapter_fingerprints(chapter_id,book_id,number,body_hash)
 VALUES(NEW.id,NEW.book_id,NEW.number,md5(NEW.title || E'\\n' || NEW.content))
 ON CONFLICT(chapter_id) DO UPDATE SET book_id=EXCLUDED.book_id,number=EXCLUDED.number,body_hash=EXCLUDED.body_hash;
 RETURN NEW;
END $$
"""
FINGERPRINT_TRIGGER="""CREATE TRIGGER storyclaw_chapter_fingerprint_write AFTER INSERT OR UPDATE OF title,content,number,book_id ON chapters FOR EACH ROW EXECUTE FUNCTION storyclaw_chapter_fingerprint()"""
event.listen(ChapterFingerprint.__table__,'after_create',DDL(FINGERPRINT_FUNCTION).execute_if(dialect='postgresql'))
event.listen(ChapterFingerprint.__table__,'after_create',DDL(FINGERPRINT_TRIGGER).execute_if(dialect='postgresql'))

class SourceIndex(Base):
    __tablename__='source_indexes'
    id:Mapped[int]=mapped_column(primary_key=True)
    source_chapter_id:Mapped[int]=mapped_column(ForeignKey('source_chapters.id',ondelete='CASCADE'),index=True)
    offset:Mapped[int]=mapped_column(Integer)
    physical_id:Mapped[int]=mapped_column(__import__('sqlalchemy').BigInteger,unique=True)
    status:Mapped[str]=mapped_column(String(24),default='staging')
    result:Mapped[dict]=mapped_column(JSON,default=dict)
