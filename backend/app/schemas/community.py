"""社区内容和公开搜索契约；只定义数据形状，不执行数据库或模型操作。"""
from datetime import datetime
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

class PostCreateIn(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    content_html: str = Field(default="",max_length=100000)
    content_text: str = Field(default="",max_length=50000)

class PostUpdateIn(BaseModel):
    title: str | None = None
    content_html: str | None = None
    content_text: str | None = None

class BookLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    book_id: int
    book_title: str = ""
    book_cover_url: str | None = None

class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    author_name: str = ""
    title: str
    content_html: str
    content_text: str
    book_links: list[BookLinkOut] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None

class PostListOut(BaseModel):
    items: list[PostOut]
    total: int
    page: int = 1
    page_size: int = 20

class SearchResultOut(BaseModel):
    posts: list[PostOut]
    books: list[dict]  # [{id, title, intro, genre, cover_url}]
    total: int
