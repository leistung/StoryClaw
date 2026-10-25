"""Version history, durable work, explicit publication and platform operations."""
revision='0009_product'
down_revision='0008_platform'
branch_labels=None
depends_on=None

def upgrade():
    from alembic import op
    from app.models.product import ChapterRevision
    from app.models.product import WorkJob
    from app.models.product import Publication
    from app.models.product import PostModeration
    from app.models.product import PostComment
    from app.models.product import PostLike
    from app.models.product import ContentReport
    from app.models.product import MembershipOrder
    from app.models.product import MembershipEntitlement
    for model in (ChapterRevision,WorkJob,Publication,PostModeration,PostComment,PostLike,ContentReport,MembershipOrder,MembershipEntitlement):
        model.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():
    raise RuntimeError('Product tables contain user revisions and operations; restore a reviewed backup instead of deleting them.')
