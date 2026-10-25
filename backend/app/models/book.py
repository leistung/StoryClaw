from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    intro: Mapped[str] = mapped_column(Text, nullable=True)
    genre: Mapped[str] = mapped_column(String(64), nullable=False)
    platforms: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array
    cover_url: Mapped[str] = mapped_column(String(512), nullable=True)
    target_chapters: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    target_words: Mapped[int] = mapped_column(Integer, nullable=False, default=60000)
    per_chapter_words: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)
    protagonist_name: Mapped[str] = mapped_column(String(64), nullable=True)
    protagonist_intro: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
