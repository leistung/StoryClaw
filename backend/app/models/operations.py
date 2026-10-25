"""Durable operational records; never store credentials in task payloads."""
from datetime import datetime
from sqlalchemy import ForeignKey,String,Text,JSON,DateTime,Integer,func
from sqlalchemy.orm import Mapped,mapped_column
from .base import Base
class SourceBlob(Base):
    __tablename__='source_blobs'
    source_id:Mapped[str]=mapped_column(ForeignKey('story_sources.id',ondelete='CASCADE'),primary_key=True)
    object_key:Mapped[str]=mapped_column(String(512),unique=True)
    digest:Mapped[str]=mapped_column(String(64))
    size:Mapped[int]=mapped_column(Integer)
class CleanupTask(Base):
    __tablename__='cleanup_tasks'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    operation_key:Mapped[str]=mapped_column(String(512),unique=True)
    kind:Mapped[str]=mapped_column(String(24))
    payload:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(24),default='queued',index=True)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    error:Mapped[str|None]=mapped_column(Text,nullable=True)
    due_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class UsageReceipt(Base):
    __tablename__='usage_receipts'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    request_id:Mapped[str]=mapped_column(String(100),unique=True)
    call_id:Mapped[str]=mapped_column(ForeignKey('model_calls.id'),index=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    input_tokens:Mapped[int]=mapped_column(Integer)
    output_tokens:Mapped[int]=mapped_column(Integer)
    supplier_reference:Mapped[str]=mapped_column(String(255))
    note:Mapped[str]=mapped_column(Text)
    credited_delta:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class ReleaseDelivery(Base):
    __tablename__='release_deliveries'
    release_id:Mapped[str]=mapped_column(ForeignKey('release_records.id',ondelete='CASCADE'),primary_key=True)
    status:Mapped[str]=mapped_column(String(24),default='scheduled',index=True)
    due_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True)
    delivered_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    error:Mapped[str|None]=mapped_column(Text,nullable=True)

class HistoryPrefix(Base):
    __tablename__='history_prefixes'
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),primary_key=True)
    upto:Mapped[int]=mapped_column(Integer,primary_key=True)
    digest:Mapped[str]=mapped_column(String(64))

from sqlalchemy import event,DDL
PREFIX_FUNCTION="""
CREATE OR REPLACE FUNCTION storyclaw_chapter_fingerprint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  PERFORM pg_advisory_xact_lock(916000000000 + OLD.book_id);
  DELETE FROM history_prefixes WHERE book_id=OLD.book_id AND upto>=OLD.number;
  RETURN OLD;
 END IF;
 PERFORM pg_advisory_xact_lock(916000000000 + NEW.book_id);
 IF TG_OP='UPDATE' THEN
  DELETE FROM history_prefixes WHERE book_id=OLD.book_id AND upto>=OLD.number;
 END IF;
 INSERT INTO chapter_fingerprints(chapter_id,book_id,number,body_hash)
 VALUES(NEW.id,NEW.book_id,NEW.number,md5(NEW.title || E'\\n' || NEW.content))
 ON CONFLICT(chapter_id) DO UPDATE SET book_id=EXCLUDED.book_id,number=EXCLUDED.number,body_hash=EXCLUDED.body_hash;
 DELETE FROM history_prefixes WHERE book_id=NEW.book_id AND upto>=NEW.number;
 RETURN NEW;
END $$
"""
event.listen(HistoryPrefix.__table__,'after_create',DDL(PREFIX_FUNCTION).execute_if(dialect='postgresql'))
event.listen(HistoryPrefix.__table__,'after_create',DDL('CREATE TRIGGER storyclaw_chapter_fingerprint_delete AFTER DELETE ON chapters FOR EACH ROW EXECUTE FUNCTION storyclaw_chapter_fingerprint()').execute_if(dialect='postgresql'))

# Prefix invalidation triggers must be installed after the base fingerprint table/function.
from .studio import ChapterFingerprint
HistoryPrefix.__table__.add_is_dependent_on(ChapterFingerprint.__table__)

class NarrativeEntity(Base):
    __tablename__='narrative_entities'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),index=True)
    name:Mapped[str]=mapped_column(String(120))
    aliases:Mapped[list]=mapped_column(JSON,default=list)
class NarrativePolicy(Base):
    __tablename__='narrative_policies'
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
class NarrativeFocus(Base):
    __tablename__='narrative_focus'
    chapter_id:Mapped[int]=mapped_column(ForeignKey('chapters.id',ondelete='CASCADE'),primary_key=True)
    persona:Mapped[str]=mapped_column(String(120))
class NarrativeFact(Base):
    __tablename__='narrative_facts'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    book_id:Mapped[int]=mapped_column(ForeignKey('books.id',ondelete='CASCADE'),index=True)
    chapter_id:Mapped[int]=mapped_column(ForeignKey('chapters.id',ondelete='CASCADE'),index=True)
    manifest_id:Mapped[int|None]=mapped_column(ForeignKey('index_manifests.id',ondelete='CASCADE'),nullable=True,index=True)
    body_hash:Mapped[str]=mapped_column(String(64))
    subject:Mapped[str]=mapped_column(String(120))
    statement:Mapped[str]=mapped_column(Text)
    quote:Mapped[str]=mapped_column(Text)
    kind:Mapped[str]=mapped_column(String(24))
    certainty:Mapped[str]=mapped_column(String(24))
    holder:Mapped[str]=mapped_column(String(120),default='')
    known_by:Mapped[list]=mapped_column(JSON,default=list)
    public:Mapped[bool]=mapped_column(default=False)
    story_time:Mapped[str]=mapped_column(String(200),default='')
    causes:Mapped[list]=mapped_column(JSON,default=list)
    valid_from:Mapped[int]=mapped_column(Integer)
    valid_until:Mapped[int|None]=mapped_column(Integer,nullable=True)
    review_status:Mapped[str]=mapped_column(String(24),default='suggested')
    version:Mapped[int]=mapped_column(Integer,default=1)
