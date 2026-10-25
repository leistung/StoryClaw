"""Pre-book discussion. A proposal never creates a book without the user's confirmation."""
import asyncio
import hashlib
import logging
import json
import re
from contextlib import suppress
from fastapi.responses import StreamingResponse
from ..database import AsyncSessionLocal
from typing import Literal
from uuid import UUID,uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.deps import get_current_user
from ..database import get_db
from ..models import User, Message, CreditsLedger
from ..services.credits import debit
from ..services.pricing import compute_cost
from ..services.platform import refresh_configs
from storyclaw.ideation.format import partial_reply

router=APIRouter(prefix='/assist',tags=['ideation'])
from storyclaw.ideation.models import Turn, ChoiceAnswer, DiscussionIn, Proposal, ChoiceQuestion, DiscussionOut

async def _legacy_ideation(data:DiscussionIn,u:User,db:AsyncSession,on_delta=None,*,defer_commit=False):
    fingerprint=hashlib.sha256(data.model_dump_json(exclude={'request_id'}).encode()).hexdigest()
    tid='idea:'+str(data.request_id)
    # Serialize retries for this user; retain successful result and request fingerprint atomically.
    await db.execute(sql_text('SELECT pg_advisory_xact_lock(:k)'),{'k':0x494445000000+u.id})
    prior=await db.scalar(select(Message).where(Message.user_id==u.id,Message.thread_id==tid,Message.role=='assistant'))
    if prior:
        saved=json.loads(prior.content)
        if saved['fingerprint']!=fingerprint:raise HTTPException(409,'请求编号已用于其他讨论，请重新提交')
        return DiscussionOut.model_validate(saved['result'])
    await db.refresh(u)
    if u.credits_balance<1:raise HTTPException(402,'积分不足，请先查看会员与积分')
    await refresh_configs(db)
    from ..services.configs import load_models
    configured=next((m for m in load_models().get('models',[]) if m.get('enabled') and m.get('id')!='custom-local'),{})
    state={'model_choice':{'kind':'business'}}
    if configured.get('format','openai_chat')=='openai_chat':
        state['response_format']={'type':'json_object'}
    try:
        from storyclaw.ideation.engine import generate_discussion
        result,ins,outs,model=await generate_discussion(data,state,on_delta)
    except (ValueError,TypeError) as exc:
        from storyclaw.metering import active_meter
        from ..services.metering import refund_format_failure
        await refund_format_failure(active_meter.get(),u.id)
        logging.getLogger(__name__).warning('Ideation validation failed: %s',exc.errors(include_input=False) if hasattr(exc,'errors') else f'{type(exc).__name__}: {getattr(exc,"msg",str(exc))}')
        raise HTTPException(502,'AI 回复格式异常，本轮未扣积分。请点击重试本次请求；你的问题仍保留。' if data.mode=='discuss' else '开书方案格式异常，本轮未扣积分，尚未创建书籍。请重试本次请求。') from exc
    except asyncio.TimeoutError as exc:raise HTTPException(504,'选题讨论超时，未创建书籍，请稍后重试') from exc
    cost=compute_cost(model,ins,outs)
    await debit(db,u,cost)
    result.credits_cost=cost
    db.add(CreditsLedger(user_id=u.id,delta=-cost,reason='ideation',model=model,in_tokens=ins,out_tokens=outs))
    db.add(Message(user_id=u.id,thread_id=tid,role='assistant',content=json.dumps({'fingerprint':fingerprint,'result':result.model_dump()},ensure_ascii=False),model=model,in_tokens=ins,out_tokens=outs,credits_cost=cost))
    if not defer_commit:await db.commit()
    return result


async def _ideation(data:DiscussionIn,u:User,db:AsyncSession,on_delta=None):
    if not data.guided:return await _legacy_ideation(data,u,db,on_delta)
    from ..models.ideation import IdeationSession
    fingerprint=hashlib.sha256(data.model_dump_json(exclude={'request_id'}).encode()).hexdigest()
    tid='idea:'+str(data.request_id)
    await db.execute(sql_text('SELECT pg_advisory_xact_lock(:k)'),{'k':0x494445000000+u.id})
    previous=await db.scalar(select(Message).where(Message.user_id==u.id,Message.thread_id==tid,Message.role=='assistant'))
    if previous:
        saved=json.loads(previous.content)
        if saved['fingerprint']!=fingerprint:raise HTTPException(409,'请求编号已用于其他讨论')
        return DiscussionOut.model_validate(saved['result'])
    if data.session_id:
        session=await db.get(IdeationSession,str(data.session_id))
        if not session or session.user_id!=u.id:raise HTTPException(404,'选题会话不存在，请重新开始讨论')
    else:
        session=IdeationSession(id=str(uuid4()),user_id=u.id,state={'round':0,'brief':data.messages[0].content,'answers':{},'history':[]})
        db.add(session)
    from storyclaw.ideation.session import advance_discussion
    async def infer(transformed):return await _legacy_ideation(transformed,u,db,on_delta,defer_commit=True)
    saved,result=await advance_discussion(session.state,data,infer,on_delta)
    result.session_id=session.id
    session.state=saved
    await db.flush()
    record=await db.scalar(select(Message).where(Message.user_id==u.id,Message.thread_id==tid,Message.role=='assistant'))
    if not record:
        record=Message(user_id=u.id,thread_id=tid,role='assistant',content='',credits_cost=0)
        db.add(record)
    record.content=json.dumps({'fingerprint':fingerprint,'result':result.model_dump()},ensure_ascii=False)
    await db.commit()
    return result


@router.post('/ideation',response_model=DiscussionOut)
async def ideation(data:DiscussionIn,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await _ideation(data,u,db)

@router.post('/ideation/stream')
async def ideation_stream(data:DiscussionIn,u:User=Depends(get_current_user)):
    uid=u.id
    async def events():
        queue=asyncio.Queue()
        async def delta(value):await queue.put(('delta',{'text':value}))
        async def produce():
            try:
                async with AsyncSessionLocal() as db:
                    user=await db.get(User,uid)
                    if not user:raise HTTPException(401,'请重新登录')
                    result=await _ideation(data,user,db,delta)
                    await queue.put(('done',result.model_dump()))
            except asyncio.CancelledError:raise
            except Exception as exc:
                detail=str(exc.detail) if isinstance(exc,HTTPException) else '本次回复未完成，请重试同一请求；尚未创建书籍'
                await queue.put(('error',{'message':detail}))
        task=asyncio.create_task(produce())
        try:
            yield 'event: start\ndata: {}\n\n'
            while True:
                try:event,payload=await asyncio.wait_for(queue.get(),timeout=15)
                except asyncio.TimeoutError:
                    yield ': keepalive\n\n';continue
                yield f'event: {event}\ndata: {json.dumps(payload,ensure_ascii=False)}\n\n'
                if event in ('done','error'):break
        finally:
            if not task.done():task.cancel()
            with suppress(asyncio.CancelledError):await task
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

from ..services.metering import metered
_legacy_ideation = metered(_legacy_ideation)
