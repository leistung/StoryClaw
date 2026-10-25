"""Platform configuration, audit and unified accounts."""
from alembic import op
import sqlalchemy as sa
revision = '0008_platform'
down_revision = '0007_adm'
branch_labels = None
depends_on = None

def upgrade():
    # create_all was used by the demo: tolerate these new tables already existing.
    from app.models.platform import PlatformConfig, PlatformEvent
    bind = op.get_bind()
    PlatformConfig.__table__.create(bind, checkfirst=True)
    PlatformEvent.__table__.create(bind, checkfirst=True)
    op.execute("UPDATE users SET version='business' WHERE version <> 'business'")
    op.alter_column('users', 'version', server_default='business')

def downgrade():
    # Unified accounts cannot be unambiguously converted back to old account versions.
    raise RuntimeError('This migration retains user data; rollback requires a reviewed backup restoration.')
