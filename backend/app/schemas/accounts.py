"""账户、登录和分享契约；只定义数据形状，不执行数据库或模型操作。"""
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    version: str
    credits_balance: int
    is_admin: bool = False

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=72)
    version: str = "business"

class LoginIn(BaseModel):
    username: str
    password: str = Field(max_length=72)

class TokenOut(BaseModel):
    user: UserOut
    token: str

class ShareOut(BaseModel):
    share_token: str

class ShareView(BaseModel):
    content: str
    model: str | None = None
    in_tokens: int | None = None
    out_tokens: int | None = None
    credits_cost: int
    created_at: str | None = None
    username: str | None = None
