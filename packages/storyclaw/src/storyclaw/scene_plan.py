from .skills import method_instructions
"""单章场景任务单：结构校验不等于文学质量或事实正确性。"""
from pydantic import BaseModel, Field

class SceneBeat(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    goal: str = Field(min_length=10, max_length=600)
    location: str = Field(min_length=1, max_length=100)
    characters: list[str] = Field(min_length=1, max_length=10)
    target_words: int = Field(ge=200, le=1500)

class ChapterScenePlan(BaseModel):
    scenes: list[SceneBeat] = Field(min_length=3, max_length=5)

async def generate_scene_plan(book: dict, context: dict, model_choice: dict):
    memory=context.get('memory_status') or {}
    if memory.get('error') or memory.get('pending_chapters'):raise ValueError('历史记忆尚未就绪，请先更新')
    import json
    from ._util import llm_respond, strip_code_fence
    system = ('你是原创小说的章节策划。只为当前章规划 3 到 5 个按顺序发生的场景，不写后续章节，不改变已确认人物关系和生死。'
              '只返回 JSON：{"scenes":[{"title":"场景名","goal":"明确的行动、阻碍、转折及结束状态，至少十字",'
              '"location":"地点","characters":["人物名"],"target_words":700}]}。'
              f'目标总字数约 {book.get("per_chapter_words",3000)}，单场景 200 到 1500 字。各场景必须推进不同事件，末场收束本章。')
    text, ins, outs, model = await llm_respond({'model_choice':model_choice},system+'\n'+method_instructions('plot-design'),json.dumps({'book':book,'chapter':context},ensure_ascii=False))
    plan=ChapterScenePlan.model_validate(json.loads(strip_code_fence(text)))
    return plan,ins,outs,model
