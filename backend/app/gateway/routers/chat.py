"""HTTP compatibility adapter. Business orchestration lives in services/chat_workflow.py."""
from fastapi import APIRouter
from app.schemas import ChapterGenerateOut
from app.schemas import ChatOut
from app.services.writing import chat_workflow as service

router = APIRouter(prefix="", tags=["chat"])

chat = service.chat
router.post("/chat", response_model=ChatOut)(chat)

chat_stream = service.chat_stream
router.post("/chat/stream")(chat_stream)

generate_chapter = service.generate_chapter
router.post("/chapters/{cid}/generate", response_model=ChapterGenerateOut)(generate_chapter)

generate_chapter_stream = service.generate_chapter_stream
router.post("/chapters/{cid}/generate-stream")(generate_chapter_stream)

modify_chapter = service.modify_chapter
router.post("/chapters/{cid}/modify", response_model=ChapterGenerateOut)(modify_chapter)

list_sessions = service.list_sessions
router.get("/chat/sessions")(list_sessions)

list_messages = service.list_messages
router.get("/messages")(list_messages)

retry = service.retry
router.post("/messages/{mid}/retry", response_model=ChatOut)(retry)

feedback = service.feedback
router.patch("/messages/{mid}/feedback")(feedback)
