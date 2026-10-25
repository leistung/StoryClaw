"""Bounded, user-owned ideation sessions."""
revision='0010_ideation'
down_revision='0009_product'
branch_labels=None
depends_on=None
def upgrade():
    from alembic import op
    from app.models.ideation import IdeationSession
    IdeationSession.__table__.create(op.get_bind(),checkfirst=True)
def downgrade():
    raise RuntimeError('Ideation sessions contain author decisions; use a reviewed backup.')
