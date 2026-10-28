"""作品、目录、大纲及章节契约；只定义数据形状，不执行数据库或模型操作。"""
from datetime import datetime
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

class BookCreateIn(BaseModel):
    title: str
    intro: str | None = None
    genre: str
    platforms: list[str] = []
    cover_url: str | None = None
    target_chapters: int = 20
    target_words: int = 60000
    per_chapter_words: int = 3000
    protagonist_name: str | None = None
    protagonist_intro: str | None = None
    # 创建后是否自动生成
    generate_outline: bool = False
    generate_plots: bool = False
    generate_characters: bool = False

class BookUpdateIn(BaseModel):
    title: str | None = None
    intro: str | None = None
    genre: str | None = None
    platforms: list[str] | None = None
    cover_url: str | None = None
    target_chapters: int | None = None
    target_words: int | None = None
    per_chapter_words: int | None = None
    protagonist_name: str | None = None
    protagonist_intro: str | None = None

class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    title: str
    intro: str | None
    genre: str
    platforms: list[str] = []
    cover_url: str | None = None
    target_chapters: int
    target_words: int
    per_chapter_words: int
    protagonist_name: str | None = None
    protagonist_intro: str | None = None
    chapter_count: int = 0
    total_words: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

class VolumeIn(BaseModel):
    name: str
    sort: int = 0

class VolumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    book_id: int
    name: str
    sort: int
    created_at: datetime | None = None

class ChapterCreateIn(BaseModel):
    title: str
    volume_id: int | None = None

class ChapterUpdateIn(BaseModel):
    expected_hash: str | None = Field(default=None, min_length=64, max_length=64)
    title: str | None = None
    content: str | None = None
    volume_id: int | None = None

class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    book_id: int
    volume_id: int | None
    number: int
    title: str
    word_count: int
    rag_status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

class ChapterDetailOut(ChapterOut):
    content: str
    content_hash: str = ""

class StatsOut(BaseModel):
    today_words: int
    month_words: int
    total_words: int

class OutlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    book_id: int
    content: dict
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class OutlineUpdateIn(BaseModel):
    content: dict
