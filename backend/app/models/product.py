"""Persistent product state. New tables preserve existing demo data."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class ChapterRevision(Base):
    __tablename__ = 'chapter_revisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey('chapters.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class WorkJob(Base):
    __tablename__ = 'work_jobs'
    __table_args__ = (UniqueConstraint('user_id','request_id',name='uq_job_request'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id',ondelete='CASCADE'), index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey('chapters.id',ondelete='CASCADE'), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Publication(Base):
    __tablename__ = 'publications'
    book_id: Mapped[int] = mapped_column(ForeignKey('books.id',ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PostModeration(Base):
    __tablename__ = 'post_moderation'
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id',ondelete='CASCADE'), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='visible')
    reason: Mapped[str] = mapped_column(String(500), default='')

class PostComment(Base):
    __tablename__ = 'post_comments'
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id',ondelete='CASCADE'),index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    content: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PostLike(Base):
    __tablename__ = 'post_likes'
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id',ondelete='CASCADE'),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),primary_key=True)

class ContentReport(Base):
    __tablename__ = 'content_reports'
    __table_args__ = (UniqueConstraint('post_id','user_id',name='uq_content_report'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id',ondelete='CASCADE'),index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default='open')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class MembershipOrder(Base):
    __tablename__ = 'membership_orders'
    __table_args__ = (UniqueConstraint('user_id','request_id',name='uq_order_request'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    package: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20),default='pending')
    note: Mapped[str] = mapped_column(String(500),default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)

class MembershipEntitlement(Base):
    __tablename__ = 'membership_entitlements'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
