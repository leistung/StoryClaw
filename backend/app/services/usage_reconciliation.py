"""Idempotent operator reconciliation from supplier evidence, never inferred usage."""
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,update
from ..models import User,CreditsLedger
from ..models.studio import ModelCall,StudioTask
from ..models.operations import UsageReceipt
from ..models.platform import PlatformEvent
from .metering import snapshot_cost
async def reconcile(db,actor,cid,data):
    from sqlalchemy import text
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),{'key':'usage-receipt:'+data.request_id})
    prior=await db.scalar(select(UsageReceipt).where(UsageReceipt.request_id==data.request_id))
    if prior:
        if (prior.call_id,prior.input_tokens,prior.output_tokens,prior.supplier_reference,prior.note)!=(cid,data.input_tokens,data.output_tokens,data.supplier_reference,data.note):raise HTTPException(409,'回执编号已用于另一份对账资料')
        return {'id':prior.id,'delta':prior.credited_delta,'idempotent':True}
    call=await db.scalar(select(ModelCall).where(ModelCall.id==cid).with_for_update())
    if not call:raise HTTPException(404,'模型调用不存在')
    if call.status not in ('unknown','needs_reconciliation'):raise HTTPException(409,'仅待对账调用可处理，不能覆盖已确认回执')
    plan=await db.scalar(select(StudioTask).where(StudioTask.id==call.plan_id).with_for_update()) if call.plan_id else None
    rates=(call.usage or {}).get('pricing')
    if not rates:raise HTTPException(409,'历史调用缺计价快照，请先人工核对价格，不能按今天价格补扣')
    if data.adjust_user_balance and call.usage.get('format_refunded'):raise HTTPException(409,'该调用已按格式失败免扣政策退款，只能登记供应商用量')
    cost=snapshot_cost(rates,data.input_tokens,data.output_tokens)
    run=None
    if call.usage.get('run_id'):
        from ..models.agent import AgentRun
        run=await db.scalar(select(AgentRun).where(AgentRun.id==call.usage['run_id']).with_for_update())
    desired=cost if data.adjust_user_balance else call.cost
    delta=call.cost-desired
    if run and run.credits_cost-delta>100:raise HTTPException(409,'补扣将超过本轮统筹预算，请选择仅登记供应商用量')
    if delta<0:
        if plan and plan.spent-delta>plan.budget:raise HTTPException(409,'补扣将超过作者授权预算，请选择仅登记供应商用量')
        result=await db.execute(update(User).where(User.id==call.user_id,User.credits_balance>=-delta).values(credits_balance=User.credits_balance+delta).returning(User.id))
        if result.scalar_one_or_none() is None:raise HTTPException(409,'用户余额不足，不能透支；可选择仅登记供应商用量')
    elif delta>0:await db.execute(update(User).where(User.id==call.user_id).values(credits_balance=User.credits_balance+delta))
    if delta:
        db.add(CreditsLedger(user_id=call.user_id,delta=delta,reason='usage-reconciliation',model=call.model,in_tokens=data.input_tokens,out_tokens=data.output_tokens))
        if plan:plan.spent-=delta
        if run:run.credits_cost-=delta
    row=UsageReceipt(id=str(uuid4()),request_id=data.request_id,call_id=cid,actor_id=actor.id,input_tokens=data.input_tokens,output_tokens=data.output_tokens,supplier_reference=data.supplier_reference,note=data.note,credited_delta=delta)
    db.add(row);call.status='reconciled';call.cost=desired;call.usage={**call.usage,'input_tokens':data.input_tokens,'output_tokens':data.output_tokens,'known':True,'supplier_reference':data.supplier_reference,'reconciled_cost':cost,'adjust_user_balance':data.adjust_user_balance}
    db.add(PlatformEvent(kind='audit',actor_id=actor.id,action='usage.reconcile',target=cid,details={'receipt_id':row.id,'delta':delta,'supplier_reference':data.supplier_reference}))
    await db.commit();return {'id':row.id,'delta':delta,'idempotent':False}
