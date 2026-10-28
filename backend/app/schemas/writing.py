"""模型写作与辅助操作契约；只定义数据形状，不执行数据库或模型操作。"""
from pydantic import BaseModel
from pydantic import Field

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
    instruction:str=Field(default='',max_length=6000)
    cursor_offset:int|None=Field(default=None,ge=0)
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
