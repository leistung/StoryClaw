"""知识入库、检索和索引状态契约；只定义数据形状，不执行数据库或模型操作。"""
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

class IngestOut(BaseModel):
    chapter_id: int
    chunks: int
    entities: int
    relations: int
    rag_status: str
    error: str | None = None

class RagQueryIn(BaseModel):
    book_id: int
    query: str
    top_k: int = 5

class RagChunkOut(BaseModel):
    text: str
    chapter_id: int
    volume_id: int | None = None
    chunk_idx: int
    score: float
    chapter_title: str = ""
    chapter_number: int = 0

class RagEntityOut(BaseModel):
    id: int
    name: str
    type: str = ""
    description: str = ""
    chapter_id: int | None = None

class RagRelationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_name: str = Field(alias="from", default="")
    to_name: str = Field(alias="to", default="")
    type: str = ""
    chapter_id: int | None = None

class RagQueryOut(BaseModel):
    chunks: list[RagChunkOut]
    entities: list[dict]
    relations: list[dict]
    query: str
    error: str | None = None

class RagStatusItem(BaseModel):
    chapter_id: int
    number: int
    title: str
    has_content: bool
    chunk_count: int
    entity_count: int
    ingested: bool

class RagStatusOut(BaseModel):
    book_id: int
    chapters: list[RagStatusItem]
    total_chunks: int = 0
    total_entities: int = 0

class RagRelatedOut(BaseModel):
    """从数据库加载：RAG 实体关系 + 相似片段."""
    entities: list[RagEntityOut] = []
    relations: list[RagRelationOut] = []
    chunks: list[RagChunkOut] = []
