"""历史对话和反馈契约；只定义数据形状，不执行数据库或模型操作。"""
from pydantic import BaseModel
from pydantic import Field

class ChatIn(BaseModel):
    book_id: int | None = Field(default=None,gt=0)
    chapter_id: int | None = Field(default=None,gt=0)
    message: str
    thread_id: str | None = None
    llm_choice: dict | None = None

class ChatOut(BaseModel):
    thread_id: str
    message_id: int
    content: str
    model: str
    in_tokens: int
    out_tokens: int
    credits_cost: int

class FeedbackIn(BaseModel):
    feedback: str | None = None
