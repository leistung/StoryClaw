"""HTTP compatibility adapter. Business orchestration lives in services/writing_workflow.py."""
from fastapi import APIRouter
from app.schemas import AnalyzeOut
from app.schemas import AssistOut
from app.schemas import ContinueOut
from app.schemas import MultiWriteOut
from app.schemas import PolishOut
from app.services.writing import writing_workflow as service

router = APIRouter(prefix="", tags=["writing-skills"])

polish_chapter = service.polish_chapter
router.post("/chapters/{cid}/polish", response_model=PolishOut)(polish_chapter)

continue_writing = service.continue_writing
router.post("/chapters/{cid}/continue", response_model=ContinueOut)(continue_writing)

multi_write = service.multi_write
router.post("/books/{bid}/multi-write", response_model=MultiWriteOut)(multi_write)

analyze_book = service.analyze_book
router.post("/books/{bid}/analyze", response_model=AnalyzeOut)(analyze_book)

assist_brainstorm = service.assist_brainstorm
router.post("/assist/brainstorm", response_model=AssistOut)(assist_brainstorm)

assist_title_generation = service.assist_title_generation
router.post("/assist/title-generation", response_model=AssistOut)(assist_title_generation)

assist_scene_enhance = service.assist_scene_enhance
router.post("/assist/scene-enhance", response_model=AssistOut)(assist_scene_enhance)

assist_dialogue_polish = service.assist_dialogue_polish
router.post("/assist/dialogue-polish", response_model=AssistOut)(assist_dialogue_polish)

assist_reading_config_gen = service.assist_reading_config_gen
router.post("/assist/reading-config-gen", response_model=AssistOut)(assist_reading_config_gen)

plan_chapter_scenes = service.plan_chapter_scenes
router.post("/chapters/{cid}/plan")(plan_chapter_scenes)
