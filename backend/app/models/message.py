from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=True)
    in_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    out_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    credits_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feedback: Mapped[str] = mapped_column(String(16), nullable=True)  # like | dislike | null
    share_token: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
