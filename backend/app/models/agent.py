"""Durable scoped agent runs and replayable, ordered observations."""
from datetime import datetime
from sqlalchemy import DateTime,ForeignKey,JSON,String,Text,Integer,UniqueConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from .base import Base

class AgentRun(Base):
    __tablename__='agent_runs'
    __table_args__=(UniqueConstraint('user_id','request_id',name='uq_agent_request'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    request_id:Mapped[str]=mapped_column(String(64))
    fingerprint:Mapped[str]=mapped_column(String(64))
    request:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(24),default='accepted',index=True)
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error:Mapped[str|None]=mapped_column(Text,nullable=True)
    decision:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    job_id:Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    event_seq:Mapped[int]=mapped_column(Integer,default=0)
    credits_cost:Mapped[int]=mapped_column(Integer,default=0)
    reserved:Mapped[int]=mapped_column(Integer,default=0)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class AgentEvent(Base):
    __tablename__='agent_events'
    __table_args__=(UniqueConstraint('run_id','seq',name='uq_agent_event_seq'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    run_id:Mapped[str]=mapped_column(ForeignKey('agent_runs.id',ondelete='CASCADE'),index=True)
    seq:Mapped[int]=mapped_column(Integer)
    type:Mapped[str]=mapped_column(String(40))
    payload:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
