from pydantic import BaseModel, ConfigDict, Field


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

# ===== P0-3 books / volumes / chapters =====
from datetime import datetime


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


# ===== P1-1 大纲 =====
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


# ===== P0-4 Agent Loop / Skill =====
class ChapterGenerateIn(BaseModel):
    prompt: str | None = None
    llm_choice: dict | None = None
    thread_id: str | None = None


class ChapterGenerateOut(BaseModel):
    chapter_id: int
    title: str
    content: str
    word_count: int
    model: str
    in_tokens: int
    out_tokens: int
    credits_cost: int
    thread_id: str
    message_id: int
    review_feedback: str = ""


# ===== P1-6 写作 Skill 全集 =====
class PolishIn(BaseModel):
    selected_text: str
    polish_goal: str | None = None
    llm_choice: dict | None = None
    thread_id: str | None = None


class PolishOut(BaseModel):
    content: str
    word_count: int
    model: str
    in_tokens: int
    out_tokens: int
    credits_cost: int
    thread_id: str
    message_id: int


class ContinueIn(BaseModel):
    prefix_text: str | None = None  # 若为空，使用章节末尾
    max_words: int = Field(default=600, ge=50, le=1500)
    llm_choice: dict | None = None
    thread_id: str | None = None


class ContinueOut(BaseModel):
    content: str
    word_count: int
    model: str
    in_tokens: int
    out_tokens: int
    credits_cost: int
    thread_id: str
    message_id: int


class MultiWriteIn(BaseModel):
    instruction: str = Field(default="", max_length=12000)
    sync_settings: bool = True
    start_number: int
    end_number: int | None = None
    count: int | None = None
    skip_existing: bool = True
    llm_choice: dict | None = None
    thread_id: str | None = None


class MultiWriteItem(BaseModel):
    chapter_id: int
    number: int
    title: str
    word_count: int
    status: str  # generated | skipped | error
    error: str | None = None


class MultiWriteOut(BaseModel):
    book_id: int
    chapters: list[MultiWriteItem]
    model: str
    total_in_tokens: int
    total_out_tokens: int
    total_credits_cost: int
    thread_id: str


class AnalyzeIn(BaseModel):
    skill: str  # plot-planning | character-development | consistency-check | book-summary | outline-planning
    book_id: int
    chapter_range: dict | None = None  # {"start","end"}
    character_name: str | None = None
    llm_choice: dict | None = None
    thread_id: str | None = None


class AnalyzeOut(BaseModel):
    report: str
    model: str
    in_tokens: int
    out_tokens: int
    credits_cost: int
    thread_id: str
    message_id: int


# ===== P0-5 RAG =====
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


# ===== P1-7 配置实体 =====
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
    kv: list[EntityKvIn] | None = None  # None=不改, []=清空, [...]=替换


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


class RagRelatedOut(BaseModel):
    """从数据库加载：RAG 实体关系 + 相似片段."""
    entities: list[RagEntityOut] = []
    relations: list[RagRelationOut] = []
    chunks: list[RagChunkOut] = []


# ===== P1-8 阅读配置 =====
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


# ===== P1-8 辅助 skill =====
class BrainstormIn(BaseModel):
    topic: str
    genre: str = ""
    direction: str = ""
    count: int = 8
    llm_choice: dict | None = None
    thread_id: str | None = None

class TitleGenIn(BaseModel):
    content: str = ""
    keywords: list[str] = []
    style: str = "classic"
    count: int = 6
    target: str = "chapter"
    llm_choice: dict | None = None
    thread_id: str | None = None

class SceneEnhanceIn(BaseModel):
    scene_text: str
    senses: list[str] = []
    mood: str = ""
    pov: str = ""
    preserve_length: bool = False
    llm_choice: dict | None = None
    thread_id: str | None = None

class DialoguePolishIn(BaseModel):
    dialogue_text: str
    characters: list[dict] = []
    goal: str = "personalize"
    preserve_info: bool = True
    llm_choice: dict | None = None
    thread_id: str | None = None

class ReadingConfigGenIn(BaseModel):
    scene: str = "default"
    user_prefs: dict = {}
    book_genre: str = ""
    llm_choice: dict | None = None
    thread_id: str | None = None

class AssistOut(BaseModel):
    content: str
    model: str
    in_tokens: int
    out_tokens: int
    credits_cost: int
    thread_id: str
    message_id: int


# ===== P1-9 社区 =====
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
