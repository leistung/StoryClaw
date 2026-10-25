"""P1-7 配置实体模型：角色/场景/物品/情节/大纲 统一存储 + 自定义键值对."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ConfigEntity(Base):
    """配置实体：character/scene/item/plot/outline 五类，用 entity_type 区分.

    每类有默认结构化字段（name/description/extra_json），自定义字段存 EntityKv.
    """
    __tablename__ = "config_entities"
    __table_args__ = (UniqueConstraint("book_id", "entity_type", "name", name="uq_config_entity_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # character: 主角/配角/反派; scene: 室内/室外/幻想; item: 武器/道具/信物;
    # plot: 主线/支线/伏笔; outline: 卷/章
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 结构化扩展字段：如角色的性格/年龄/关系，情节的起止章号等
    extra_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EntityKv(Base):
    """自定义键值对：entity_type + entity_id 定位实体，key/value 存自定义属性."""
    __tablename__ = "entity_kv"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "key", name="uq_entity_kv"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
