from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class Turn(BaseModel):
    role: Literal['user','assistant']
    content: str=Field(min_length=1,max_length=6000)
class ChoiceAnswer(BaseModel):
    id: Literal['genre','tone','length','subgenre','protagonist','conflict']
    values: list[str]=Field(default_factory=list,max_length=14)
    custom: str=Field(default='',max_length=500)
class DiscussionIn(BaseModel):
    request_id: UUID
    messages: list[Turn]=Field(min_length=1,max_length=20)
    genre: Literal['都市','玄幻','仙侠','历史','科幻','悬疑','言情','其他']|None=None
    mode: Literal['discuss','proposal','revise']='discuss'
    guided: bool=False
    session_id: UUID|None=None
    answers: list[ChoiceAnswer]=Field(default_factory=list,max_length=6)
class Proposal(BaseModel):
    title: str=Field(min_length=1,max_length=200)
    intro: str=Field(min_length=20,max_length=3000)
    genre: str=Field(min_length=1,max_length=40)
    protagonist_name: str=Field(min_length=1,max_length=100)
    protagonist_intro: str=Field(min_length=10,max_length=1500)
    target_chapters: int=Field(ge=5,le=3000)
    per_chapter_words: int=Field(ge=1000,le=5000)
class ChoiceQuestion(BaseModel):
    id: str=''
    question: str=Field(min_length=2,max_length=200)
    description: str=Field(default='',max_length=600)
    options: list[str]=Field(min_length=2,max_length=20)
    multiple: bool=False

class DiscussionOut(BaseModel):
    reply: str=Field(min_length=1,max_length=6000)
    proposal: Proposal|None=None
    questions: list[ChoiceQuestion]=Field(default_factory=list,max_length=4)
    session_id: str|None=None
    stage: str='discussion'
    question_round: int=Field(default=0,ge=0,le=3)
    credits_cost: int=0

