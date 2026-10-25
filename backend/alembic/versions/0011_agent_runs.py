"""Scoped agent runs and replayable events; does not alter manuscripts."""
revision='0011_agent_runs'
down_revision='0010_ideation'
branch_labels=None
depends_on=None

def upgrade():
    from alembic import op
    from app.models.agent import AgentRun,AgentEvent
    for model in (AgentRun,AgentEvent):model.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():
    raise RuntimeError('Agent runs contain author decisions; use an explicit reviewed retention migration.')
