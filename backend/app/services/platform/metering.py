"""Host-side reservations and actual per-call ledgers shared by all creative workflows."""
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from functools import wraps
import inspect
from contextlib import asynccontextmanager
from sqlalchemy import select,update,event
from sqlalchemy.orm import Session
from fastapi import HTTPException
from storyclaw.models.metering import Meter
from storyclaw.models.metering import active_meter
from app.database import AsyncSessionLocal
from app.models import User
from app.models import CreditsLedger
from app.models.studio import ModelCall
from app.models.studio import StudioTask
from app.services.platform.pricing import compute_cost

@event.listens_for(Session,'before_flush')
def suppress_legacy_summaries(session,flush_context,instances):
    meter=active_meter.get()
    if meter and meter.calls:
        for obj in list(session.new):
            if isinstance(obj,CreditsLedger) and obj.reason in ('consume','multi-write','chapter-plan','chapter-outline','story-design','ideation'):session.expunge(obj)

def pricing_snapshot(model):
    from app.services.platform.configs import load_pricing
    config=load_pricing();defaults=config.get('defaults',{})
    if model.startswith('embedding:'):return {'embedding_rate':float(defaults.get('embedding_credits_per_1k',1))}
    return {'rates':config.get('pricing',{}).get(model,{}),'base':defaults.get('price_base','per_1k_tokens')}

def snapshot_cost(snapshot,ins,outs):
    import math
    if not (ins or outs):return 0
    if 'embedding_rate' in snapshot:return max(1,math.ceil(ins*snapshot['embedding_rate']/1000))
    divisor={'per_token':1,'per_1k_tokens':1000,'per_1m_tokens':1000000}.get(snapshot['base'],1000)
    rate=snapshot['rates']
    return max(1,math.ceil((ins*rate['input_price']+outs*rate['output_price'])/divisor))

def price(model,ins,outs):
    if model.startswith('embedding:'):
        from app.services.platform.configs import load_pricing
        import math
        rate=float(load_pricing().get('defaults',{}).get('embedding_credits_per_1k',1))
        return max(1,math.ceil(ins*rate/1000)) if ins else 0
    return compute_cost(model,ins,outs)

@asynccontextmanager
async def usage_scope(uid,job_id=None,plan_id=None,run_id=None):
    if active_meter.get() is not None:
        yield active_meter.get();return
    async def reserve(model,ins,outs):
        amount=price(model,ins,outs);rate_snapshot=pricing_snapshot(model)
        async with AsyncSessionLocal() as db:
            if run_id:
                from app.models.agent import AgentRun
                run=await db.scalar(select(AgentRun).where(AgentRun.id==run_id,AgentRun.user_id==uid).with_for_update())
                if not run or run.status!='running':raise HTTPException(409,'创作请求已停止')
                from sqlalchemy import func
                held=await db.scalar(select(func.coalesce(func.sum(ModelCall.reserved),0)).where(ModelCall.usage['run_id'].as_string()==run_id,ModelCall.status=='reserved'))
                if run.credits_cost+held+amount>100:raise HTTPException(402,'本轮统筹预算不足以预留下一次调用，已停止')
            if plan_id:
                plan=await db.scalar(select(StudioTask).where(StudioTask.id==plan_id).with_for_update())
                if not plan or plan.status not in ('queued','running'):raise HTTPException(409,'连续计划已暂停或取消')
                held=await db.scalar(select(__import__('sqlalchemy').func.coalesce(__import__('sqlalchemy').func.sum(ModelCall.reserved),0)).where(ModelCall.plan_id==plan_id,ModelCall.status=='reserved'))
                if plan.spent+held+amount>plan.budget:raise HTTPException(402,'计划剩余预算不足以预留下一次模型调用，已停止')
            result=await db.execute(update(User).where(User.id==uid,User.credits_balance>=amount).values(credits_balance=User.credits_balance-amount).returning(User.id))
            if result.scalar_one_or_none() is None:raise HTTPException(402,'积分不足，未调用模型')
            row=ModelCall(id=str(uuid4()),user_id=uid,job_id=job_id,plan_id=plan_id,model=model,status='reserved',reserved=amount,cost=0,usage={'pricing':rate_snapshot,**({'run_id':run_id} if run_id else {})},lease_until=datetime.now(timezone.utc)+timedelta(minutes=4))
            db.add(row);await db.commit();return row.id
    async def settle(cid,usage,complete):
        async with AsyncSessionLocal() as db:
            row=await db.scalar(select(ModelCall).where(ModelCall.id==cid).with_for_update())
            if row.status!='reserved':return row.cost
            if plan_id:await db.scalar(select(StudioTask).where(StudioTask.id==plan_id).with_for_update())
            known=usage.get('input_tokens') is not None or usage.get('output_tokens') is not None
            rate_snapshot=(row.usage or {}).get('pricing') or pricing_snapshot(row.model)
            cost=snapshot_cost(rate_snapshot,int(usage.get('input_tokens',0)),int(usage.get('output_tokens',0))) if known else 0
            if cost>row.reserved:
                # Provider exceeded configured caps; record for reconciliation, never silently overdraw.
                row.status='needs_reconciliation';cost=row.reserved
            else:row.status='settled' if known and complete else 'unknown'
            await db.execute(update(User).where(User.id==uid).values(credits_balance=User.credits_balance+row.reserved-cost))
            row.reserved=0;row.cost=cost;row.usage={**(row.usage or {}),**usage,'known':known,'complete':complete,'pricing':rate_snapshot}
            if plan_id:
                await db.execute(update(StudioTask).where(StudioTask.id==plan_id).values(spent=StudioTask.spent+cost))
            if run_id:
                from app.models.agent import AgentRun
                await db.execute(update(AgentRun).where(AgentRun.id==run_id).values(credits_cost=AgentRun.credits_cost+cost))
            db.add(CreditsLedger(user_id=uid,delta=-cost,reason='model-call',model=row.model,in_tokens=int(usage.get('input_tokens',0)),out_tokens=int(usage.get('output_tokens',0))))
            await db.commit();return cost
    meter=Meter(reserve,settle);token=active_meter.set(meter)
    try:yield meter
    finally:active_meter.reset(token)

def metered(fn):
    signature=inspect.signature(fn,eval_str=True)
    @wraps(fn)
    async def wrapped(*args,**kwargs):
        bound=signature.bind(*args,**kwargs);user=bound.arguments.get('u')
        if user is None:return await fn(*args,**kwargs)
        async with usage_scope(user.id) as meter:response=await fn(*args,**kwargs)
        if meter.calls:
            if hasattr(response,'credits_cost'):response.credits_cost=meter.spent
            elif isinstance(response,dict):response['credits_cost']=meter.spent
        from starlette.responses import StreamingResponse
        if isinstance(response,StreamingResponse):
            original=response.body_iterator
            async def body():
                async with usage_scope(user.id):
                    async for chunk in original:yield chunk
            response.body_iterator=body()
        return response
    wrapped.__signature__=signature
    return wrapped

async def reclaim_expired():
    async with AsyncSessionLocal() as db:
        rows=list(await db.scalars(select(ModelCall).where(ModelCall.status=='reserved',ModelCall.lease_until<datetime.now(timezone.utc)).with_for_update(skip_locked=True)))
        for row in rows:
            await db.execute(update(User).where(User.id==row.user_id).values(credits_balance=User.credits_balance+row.reserved))
            row.reserved=0;row.status='unknown';row.usage={**(row.usage or {}),'known':False,'reason':'worker_interrupted'}
        await db.commit()

async def refund_format_failure(meter,uid):
    """Preserve the product's no-charge policy for unusable ideation JSON; retain supplier usage."""
    if not meter or not meter.call_ids:return
    async with AsyncSessionLocal() as db:
        rows=list(await db.scalars(select(ModelCall).where(ModelCall.id.in_(meter.call_ids),ModelCall.user_id==uid).with_for_update()))
        for row in rows:
            if row.usage.get('format_refunded'):continue
            amount=row.cost
            if amount:
                await db.execute(update(User).where(User.id==uid).values(credits_balance=User.credits_balance+amount))
                db.add(CreditsLedger(user_id=uid,delta=amount,reason='format-refund',model=row.model))
            row.cost=0;row.usage={**row.usage,'format_refunded':True,'original_credits_cost':amount}
        await db.commit()
    meter.spent=0
