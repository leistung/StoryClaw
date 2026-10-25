"""HTTP compatibility adapter. Business orchestration lives in services/knowledge_workflow.py."""
from fastapi import APIRouter
from ..schemas import IngestOut, RagQueryOut, RagStatusOut
from ..services import knowledge_workflow as service

router = APIRouter(prefix="", tags=["rag"])

ingest_chapter_endpoint = service.ingest_chapter_endpoint
router.post("/chapters/{cid}/ingest", response_model=IngestOut)(ingest_chapter_endpoint)

rag_query = service.rag_query
router.post("/rag/query", response_model=RagQueryOut)(rag_query)

rag_status = service.rag_status
router.get("/books/{bid}/rag-status", response_model=RagStatusOut)(rag_status)
