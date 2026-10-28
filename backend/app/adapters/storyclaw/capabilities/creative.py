"""短文本写作与候选生成，不负责采用。公共权限边界由 Ports 统一校验。"""
from fastapi import HTTPException
from sqlalchemy import update
from storyclaw.contracts import CapabilityResult
from app.models import User
from app.models.agent import AgentRun
from app.services.agent.manuscript_references import resolve_reference
from app.services.writing.revisions import chapter_hash

async def execute(ctx, name, arguments):
    db = ctx.db
    book = ctx.book
    chapter = ctx.chapter
    scope = ctx.ports.request.scope
    if name in ('idea.brainstorm', 'title.suggest', 'text.polish', 'text.continue', 'text.scene_enhance', 'text.dialogue_polish'):
        from app.services.writing import writing_workflow as writing
        from app.schemas import BrainstormIn
        from app.schemas import TitleGenIn
        from app.schemas import PolishIn
        from app.schemas import ContinueIn
        from app.schemas import SceneEnhanceIn
        from app.schemas import DialoguePolishIn
        from storyclaw.workflows.continuity import prose
        user = await db.get(User, ctx.ports.uid)
        if user.credits_balance < 1:
            raise HTTPException(402, '积分不足')
        reference = next((r for r in ctx.ports.request.references if r.kind == ('cursor' if name == 'text.continue' else 'selection')), None)
        span = resolve_reference(chapter.content, reference) if reference and chapter else None
        text = span['text'] if span and name != 'text.continue' else arguments.get('selected_text', '')
        if name.startswith('text.'):
            if not chapter:
                raise ValueError('请先选择当前章节')
            if name != 'text.continue' and (not text.strip()):
                raise ValueError('请先引用要修改的正文片段，或明确指定选中内容')
            if text and text not in prose(chapter.content):
                raise ValueError('指定片段不在当前正文，请重新选择，不会整章替换')
        instruction = arguments['instruction']
        if name == 'idea.brainstorm':
            result = await writing.assist_brainstorm(BrainstormIn(topic=instruction + '\n作品约定：' + (book.intro or '')[:2000], genre=book.genre), user, db)
        elif name == 'title.suggest':
            result = await writing.assist_title_generation(TitleGenIn(content=prose(chapter.content)[:6000] if chapter else book.intro or '', keywords=[instruction], target='chapter' if chapter else 'book'), user, db)
        elif name == 'text.polish':
            result = await writing.polish_chapter(chapter.id, PolishIn(selected_text=text, polish_goal=instruction), user, db)
        elif name == 'text.continue':
            result = await writing.continue_writing(chapter.id, ContinueIn(prefix_text=prose(chapter.content)[:span['start']] if span else prose(chapter.content), cursor_offset=span['start'] if span else None, instruction=instruction, max_words=arguments['max_words']), user, db)
        elif name == 'text.scene_enhance':
            result = await writing.assist_scene_enhance(SceneEnhanceIn(scene_text=text, mood=instruction), user, db)
        else:
            result = await writing.assist_dialogue_polish(DialoguePolishIn(dialogue_text=text, goal=instruction), user, db)
        await db.execute(update(AgentRun).where(AgentRun.id == ctx.ports.rid).values(credits_cost=AgentRun.credits_cost + result.credits_cost))
        await db.commit()
        return CapabilityResult(content=result.content, data={'artifact': True, 'kind': name, 'adopted': False, 'selected_text': text, 'chapter_id': scope.chapter_id, 'base_hash': chapter_hash(chapter) if chapter else None, 'range': span, 'credits_cost': result.credits_cost})
