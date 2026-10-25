from __future__ import annotations
import uuid
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.context.builder import count_words
from storyclaw.runtime.execution import run_agent
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Book
from app.models import Chapter
from app.models import CreditsLedger
from app.models import Message
from app.models import User
from app.schemas import MultiWriteIn
from app.schemas import MultiWriteItem
from app.schemas import MultiWriteOut
from app.services.platform.credits import debit
from app.services.writing.revisions import snapshot
from app.services.writing.revisions import assert_editable
from app.services.writing.revisions import chapter_hash
from app.services.writing.revisions import guard_write
from app.services.platform import pricing as pricing_svc
from app.services.knowledge.memory import load_user_memory
from app.services.platform.skill_loader import build_write_context

from .context import _load_outline
from .context import _model_choice

async def multi_write(
    bid: int, data: MultiWriteIn,
    u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """write-multi-chapters skill：批量生成多章正文。"""
    b = await db.get(Book, bid)
    if not b or b.user_id != u.id:
        raise HTTPException(404, "书籍不存在")

    from app.services.writing.planning import require_outline
    await require_outline(db,bid)

    start = data.start_number
    if data.end_number:
        end = data.end_number
    elif data.count:
        end = start + data.count - 1
    else:
        end = start
    if end < start:
        raise HTTPException(400, "end_number 不能小于 start_number")
    if end - start > 20:
        raise HTTPException(400, "单次批量不超过 20 章")

    thread_id = data.thread_id or uuid.uuid4().hex
    mc = _model_choice(u, data.llm_choice)
    user_mem = await load_user_memory(u.id, db)
    outline = await _load_outline(db, bid)
    if outline.get('planning_mode')=='serial':raise HTTPException(409,'连载模式请逐章确认章纲并写作；不批量预写未确认的章节')

    items: list[MultiWriteItem] = []
    total_in, total_out, total_cost = 0, 0, 0
    model_id = ""

    # 加载范围内章节
    rs = await db.scalars(select(Chapter).where(
        Chapter.book_id == bid, Chapter.number >= start, Chapter.number <= end
    ).order_by(Chapter.number))
    chapters_by_num = {c.number: c for c in rs}

    # 若章节不存在，自动创建
    for num in range(start, end + 1):
        if num not in chapters_by_num:
            nc = Chapter(book_id=bid, number=num, title=f"第{num}章 待定", content="", word_count=0)
            db.add(nc)
            await db.commit()
            await db.refresh(nc)
            chapters_by_num[num] = nc

    uid=u.id
    target_words=b.per_chapter_words
    chapter_ids={number:chapter.id for number,chapter in chapters_by_num.items()}
    for cid in chapter_ids.values():await assert_editable(db,cid)
    prev_summary = ""
    for num in range(start,end+1):
        ch=await db.get(Chapter,chapter_ids[num])
        cid=ch.id;title=ch.title;original_hash=chapter_hash(ch)
        if data.skip_existing and ch.content:
            items.append(MultiWriteItem(chapter_id=cid,number=num,title=title,word_count=ch.word_count,status="skipped"))
            prev_summary=ch.content[-600:]
            continue
        try:
            ctx=await build_write_context(uid,bid,cid,db)
            outline_node=next((node for vol in outline.get('volumes',[]) for node in vol.get('chapters',[]) if int(node.get('number',0))==num),{})
            ctx['chapter_meta']={'id':cid,'number':num,'title':title,'per_chapter_words':target_words}
            ctx['outline_node']=outline_node
            ctx['prev_chapter_summary']=prev_summary or ctx.get('prev_chapter_summary','')
            final=await run_agent({'user_id':uid,'book_id':bid,'chapter_id':cid,'thread_id':thread_id,
                'messages':[{'role':'user','content':f'请撰写第{num}章 {title}。目标{target_words}字，不超出本章大纲。\n{data.instruction}'}],
                'model_choice':mc,'user_memory':user_mem,'context':ctx,'current_content':'','intent':'write'},thread_id)
            content=final.get('draft_content','')
            if not content:raise HTTPException(502,'本章未返回正文')
            await guard_write(db,ch,original_hash)
            tu=final.get('token_usage') or {}
            ti,to=int(tu.get('in_tokens',0)),int(tu.get('out_tokens',0));mid=tu.get('model_id','')
            cost=pricing_svc.compute_cost(mid,ti,to)
            payer=await db.get(User,uid)
            await debit(db,payer,cost)
            db.add(CreditsLedger(user_id=uid,delta=-cost,reason='multi-write',model=mid,in_tokens=ti,out_tokens=to))
            await snapshot(db,ch,'ai-batch')
            ch.content=content;ch.word_count=count_words(content);ch.rag_status='pending'
            if title.endswith('待定') and outline_node.get('title'):ch.title=outline_node['title']
            result_title=ch.title;wc=ch.word_count
            # Persist the chapter, its previous version, and debit as one unit.
            await db.commit()
            total_in+=ti;total_out+=to;total_cost+=cost;model_id=mid or model_id
            prev_summary=content[-600:]
            items.append(MultiWriteItem(chapter_id=cid,number=num,title=result_title,word_count=wc,status='generated'))
            if data.sync_settings:
                from app.services.writing.setting_sync import launch
                launch(bid,cid,uid,mc)
        except Exception as exc:
            await db.rollback()
            error=str(exc.detail) if isinstance(exc,HTTPException) else '本章生成失败，请核对内容后重试'
            items.append(MultiWriteItem(chapter_id=cid,number=num,title=title,word_count=0,status='error',error=error))
    summary=f"[批量生成] 第{start}-{end}章："+', '.join(f'第{it.number}章{it.status}' for it in items)
    db.add(Message(user_id=uid,thread_id=thread_id,role='assistant',content=summary,model=model_id,
                   in_tokens=total_in,out_tokens=total_out,credits_cost=total_cost))
    await db.commit()
    return MultiWriteOut(book_id=bid,chapters=items,model=model_id,total_in_tokens=total_in,
                         total_out_tokens=total_out,total_credits_cost=total_cost,thread_id=thread_id)


