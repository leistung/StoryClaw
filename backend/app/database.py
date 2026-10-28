import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

pool_options = {}
if os.environ.get('STORYCLAW_PROCESS_ROLE') == 'worker':
    # Allow every active job to settle usage while holding its working session,
    # plus headroom for heartbeats/plans. Keep this finite across replicas.
    from app.core.capacity import worker_slots
    pool_options = {'pool_size': 5, 'max_overflow': max(10, 2 * worker_slots() + 8 - 5)}
engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True, **pool_options)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
