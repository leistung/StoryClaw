"""HTTP compatibility adapter. Business orchestration lives in services/outline_workflow.py."""
from fastapi import APIRouter
from app.schemas import OutlineOut
from app.services.writing import outline_workflow as service

router = APIRouter(prefix="/books", tags=["outlines"])

generate_outline = service.generate_outline
router.post("/{bid}/outline/generate", response_model=OutlineOut)(generate_outline)

get_outline = service.get_outline
router.get("/{bid}/outline", response_model=OutlineOut)(get_outline)

update_outline = service.update_outline
router.put("/{bid}/outline", response_model=OutlineOut)(update_outline)

confirm_outline = service.confirm_outline
router.post("/{bid}/outline/confirm", response_model=OutlineOut)(confirm_outline)
