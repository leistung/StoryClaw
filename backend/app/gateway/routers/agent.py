"""Agent Run HTTP adapter. Execution occurs in the durable queue, not the browser connection."""
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storyclaw.contracts import AgentRequest
from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.models import Chapter
from app.models.agent import AgentRun
from app.models.agent import AgentEvent
from app.models.product import WorkJob
from app.services.agent import agent_runs as service

router=APIRouter(prefix='/agent',tags=['agent-runs'])

from app.services.agent.agent_decisions import owned
from app.adapters.storyclaw.agent import BackendStoryPorts
from storyclaw.agents.lead_agent.agent import StoryClaw

def facade(rid,u):return StoryClaw(BackendStoryPorts(rid,u.id,None))

@router.post('/runs')
async def create(request:AgentRequest,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await service.create(request,u.id,db)

@router.get('/runs')
async def list_runs(book_id:int|None=None,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    q=select(AgentRun).where(AgentRun.user_id==u.id)
    if book_id is not None:q=q.where(AgentRun.request['scope']['book_id'].as_integer()==book_id)
    rows=await db.scalars(q.order_by(AgentRun.created_at.desc()).limit(100))
    return [service.out(r) for r in rows]

@router.get('/runs/{rid}')
async def status(rid:str,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await facade(rid,u).status(rid)

@router.get('/runs/{rid}/events')
async def events(rid:str,after_seq:int=Query(0,ge=0),u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await facade(rid,u).events(rid,after_seq)

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    decision_id:str
    accept:bool

@router.post('/runs/{rid}/decisions')
async def decide(rid:str,data:Decision,u:User=Depends(get_current_user)):
    return await facade(rid,u).resume(rid,data.model_dump())

class RevisePlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    decision_id:str
    feedback:str=Field(min_length=1,max_length=6000)

@router.post('/runs/{rid}/plan')
async def revise_plan(rid:str,data:RevisePlan,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    row=await owned(rid,u,db,True)
    if row.status!='waiting_author' or (row.decision or {}).get('kind')!='creation_plan' or row.decision['id']!=data.decision_id:
        raise HTTPException(409,'计划已变化，请刷新后重试')
    active=await db.scalar(select(AgentRun.id).where(AgentRun.user_id==u.id,AgentRun.status.in_(['accepted','running'])))
    if active:raise HTTPException(409,'请等待当前创作请求结束后再调整计划')
    row.decision={**row.decision,'feedback':data.feedback}
    row.status='accepted';row.result=None;row.error=None;row.lease_until=None
    await service.event(db,row,'plan.revised',{'feedback':data.feedback,'label':'已收到补充，重新拟订计划'})
    await db.commit();return service.out(row)

@router.post('/runs/{rid}/cancel')
async def cancel(rid:str,u:User=Depends(get_current_user)):
    return await facade(rid,u).cancel(rid)

class AdoptCandidate(BaseModel):
    expected_hash:str=Field(min_length=64,max_length=64)

@router.post('/runs/{rid}/adopt')
async def adopt_candidate(rid:str,data:AdoptCandidate,u:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    from app.services.agent.candidates import adopt_candidate as adopt
    return await adopt(rid, data.expected_hash, u, db)
