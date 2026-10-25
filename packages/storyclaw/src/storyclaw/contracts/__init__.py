"""Transport-independent agent contracts. No SQL or HTTP dependencies."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class Scope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    book_id: int | None = Field(default=None, gt=0)
    chapter_id: int | None = Field(default=None, gt=0)

class ExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    actor_id: int = Field(gt=0)

class AgentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9-]+$')
    entry: Literal['chat','command'] = 'chat'
    message: str = Field(default='',max_length=12000)
    command: str | None = None
    payload: dict[str,Any] = Field(default_factory=dict)
    scope: Scope = Field(default_factory=Scope)
    conversation_id: str | None = Field(default=None,max_length=64,pattern=r'^[A-Za-z0-9-]+$')

class ToolCall(BaseModel):
    name: str
    arguments: dict[str,Any] = Field(default_factory=dict)

class ModelTurn(BaseModel):
    text: str = ''
    calls: list[ToolCall] = Field(default_factory=list)

class CapabilityResult(BaseModel):
    status: Literal['succeeded','waiting_author','waiting_task'] = 'succeeded'
    content: str = ''
    data: dict[str,Any] = Field(default_factory=dict)

class AgentOutcome(BaseModel):
    status: Literal['succeeded','waiting_author','waiting_task','partial']
    content: str
    data: dict[str,Any] = Field(default_factory=dict)
