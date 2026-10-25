"""RAG 数据模型：向量切片 + 实体 + 关系（PostgreSQL 存储，开发期用内存 cosine 检索）."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class RagChunk(Base):
    """章节文本切片 + embedding（JSON 存 float 数组）."""
    __tablename__ = "rag_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False, index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False, index=True)
    volume_id: Mapped[int | None] = mapped_column(ForeignKey("volumes.id"), nullable=True)
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)  # 章节内序号
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # float[1024]
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagEntity(Base):
    """实体节点：人物/场景/物品/情节/伏笔."""
    __tablename__ = "rag_entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # character/scene/item/plot/hook
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagRelation(Base):
    """实体关系：KNOWS/LOCATED_IN/OWNS/RELATES_TO/FORESHADOWS/RESOLVES/APPEARS_IN."""
    __tablename__ = "rag_relations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False, index=True)
    from_entity_id: Mapped[int] = mapped_column(ForeignKey("rag_entities.id"), nullable=False, index=True)
    to_entity_id: Mapped[int] = mapped_column(ForeignKey("rag_entities.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
