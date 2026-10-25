from __future__ import annotations
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import CreditsLedger
from app.models import User
from app.services.platform.credits import debit
from app.services.platform import pricing as pricing_svc
from app.services.platform.skill_loader import build_write_context
from app.services.platform.metering import metered

from .context import _model_choice

async def plan_chapter_scenes(cid: int, u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """在生成正文前，生成并保存 3~5 个有目标和字数分配的场景。"""
    from storyclaw.workflows.scene_plan import generate_scene_plan
    from app.models import ConfigEntity
    chapter = await db.get(Chapter, cid)
    if not chapter:
        raise HTTPException(404, "章节不存在")
    book = await db.get(Book, chapter.book_id)
    if not book or book.user_id != u.id:
        raise HTTPException(404, "章节不存在")
    from app.services.writing.planning import require_outline
    await require_outline(db,book.id)
    from app.services.writing.serial import require_blueprint
    await require_blueprint(db,chapter)
    ctx = await build_write_context(u.id, book.id, cid, db)
    try:
        plan,in_t,out_t,model_id=await generate_scene_plan({'title':book.title,'intro':book.intro,'per_chapter_words':book.per_chapter_words},ctx,_model_choice(u,None))
    except (ValueError, TypeError) as exc:
        raise HTTPException(502, "场景任务单未通过结构校验，请重试") from exc
    name = f"第{chapter.number}章场景任务单"
    row = await db.scalar(select(ConfigEntity).where(ConfigEntity.book_id == book.id,
        ConfigEntity.entity_type == "plot", ConfigEntity.name == name))
    if not row:
        row = ConfigEntity(book_id=book.id, entity_type="plot", name=name, category="chapter-plan", description="")
        db.add(row)
    from app.services.writing.serial import inputs
    from storyclaw.workflows.serial import digest
    if (await inputs(db,chapter))[3]!=ctx.get('dependency_hash'):raise HTTPException(409,'规划期间参考资料变化，请重新规划场景')
    row.extra_json = {**plan.model_dump(),'_dependencies':ctx.get('dependency_hash'),'_blueprint_hash':digest(ctx.get('outline_node'))}
    row.description = "；".join(s.title for s in plan.scenes)
    cost = pricing_svc.compute_cost(model_id, in_t, out_t)
    await debit(db, u, cost)
    db.add(CreditsLedger(user_id=u.id, delta=-cost, reason="chapter-plan", model=model_id, in_tokens=in_t, out_tokens=out_t))
    await db.commit()
    return {"chapter_id": cid, **plan.model_dump(), "model": model_id, "in_tokens": in_t,
            "out_tokens": out_t, "credits_cost": cost}


plan_chapter_scenes = metered(plan_chapter_scenes)

