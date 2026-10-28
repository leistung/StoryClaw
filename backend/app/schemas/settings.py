"""作者设定与阅读偏好契约；只定义数据形状，不执行数据库或模型操作。"""
from datetime import datetime
from pydantic import BaseModel
from pydantic import ConfigDict

class EntityKvIn(BaseModel):
    key: str
    value: str = ""

class EntityKvOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entity_type: str
    entity_id: int
    key: str
    value: str

class ConfigEntityCreateIn(BaseModel):
    name: str
    category: str = ""
    description: str = ""
    image_url: str | None = None
    extra_json: dict | None = None
    kv: list[EntityKvIn] = []

class ConfigEntityUpdateIn(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    image_url: str | None = None
    extra_json: dict | None = None
    sort_order: int | None = None
    kv: list[EntityKvIn] | None = None

class ConfigEntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    book_id: int
    entity_type: str
    category: str
    name: str
    description: str
    image_url: str | None
    extra_json: dict | None
    sort_order: int
    kv: list[EntityKvOut] = []

class ConfigEntityListOut(BaseModel):
    book_id: int
    entity_type: str
    items: list[ConfigEntityOut]
    total: int

class ReadingConfigIn(BaseModel):
    name: str
    scene: str = "default"
    config_json: dict
    book_id: int | None = None
    is_default: bool = False

class ReadingConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    book_id: int | None
    name: str
    scene: str
    config_json: dict
    is_default: bool
    created_at: datetime | None = None

class ReadingConfigListOut(BaseModel):
    items: list[ReadingConfigOut]
    total: int
