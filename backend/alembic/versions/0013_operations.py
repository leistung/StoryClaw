"""Private source blobs, durable cleanup, usage receipts and release delivery."""
revision='0013_operations'
down_revision='0012_studio'
branch_labels=None
depends_on=None
def upgrade():
    from alembic import op
    from app.models.operations import SourceBlob,CleanupTask,UsageReceipt,ReleaseDelivery,HistoryPrefix,NarrativeEntity,NarrativePolicy,NarrativeFocus,NarrativeFact
    for model in (SourceBlob,CleanupTask,UsageReceipt,ReleaseDelivery,HistoryPrefix,NarrativeEntity,NarrativePolicy,NarrativeFocus,NarrativeFact):model.__table__.create(op.get_bind(),checkfirst=True)
def downgrade():raise RuntimeError('Operational receipts require an explicit retention migration.')
