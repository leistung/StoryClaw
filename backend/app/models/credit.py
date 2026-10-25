from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class UserLLMConfig(Base):
    __tablename__ = "user_llm_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)  # openai_chat | anthropic | openai_responses
    base_url: Mapped[str] = mapped_column(String(512), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    is_default: Mapped[bool] = mapped_column(default=False)
    # ===== 向量化（embedding）配置：单独指定 embedding 端点/模型 =====
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=True)
    embedding_base_url: Mapped[str] = mapped_column(String(512), nullable=True)
    embedding_api_key_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditsLedger(Base):
    __tablename__ = "credits_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)  # + 充值 / - 消耗
    reason: Mapped[str] = mapped_column(String(64), nullable=False)  # recharge | consume | bonus
    model: Mapped[str] = mapped_column(String(128), nullable=True)
    in_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    out_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    ref_msg_id: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
