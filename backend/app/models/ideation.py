from datetime import datetime
from sqlalchemy import String,ForeignKey,JSON,DateTime,func
from sqlalchemy.orm import Mapped,mapped_column
from .base import Base
class IdeationSession(Base):
    __tablename__='ideation_sessions'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    state:Mapped[dict]=mapped_column(JSON,default=dict)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())
