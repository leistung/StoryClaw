"""平台模型配置契约；只定义数据形状，不执行数据库或模型操作。"""
from pydantic import BaseModel
from pydantic import ConfigDict

class LLMConfigIn(BaseModel):
    name: str
    format: str
    base_url: str | None = None
    model: str
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int = 8192
    is_default: bool = False
    # embedding（向量化）配置：可选，独立于对话 LLM
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None

class LLMConfigUpdate(BaseModel):
    name: str | None = None
    format: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_default: bool | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None

class LLMConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    format: str
    base_url: str | None
    model: str
    temperature: float
    max_tokens: int
    is_default: bool
    has_key: bool
    # embedding 配置输出：不返回明文 key，仅返回是否已配置
    embedding_model: str | None
    embedding_base_url: str | None
    has_embedding_key: bool
