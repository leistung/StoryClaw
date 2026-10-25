"""P1-8 阅读配置模型：存储用户阅读配置模板."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ReadingConfig(Base):
    """阅读配置模板：字号/边距/背景/字色/亮度等."""
    __tablename__ = "reading_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # 模板名称
    scene: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)  # 完整配置
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
