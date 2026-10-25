"""Provenance, takeover, branches, serial plans and release snapshots."""
revision='0012_studio'
down_revision='0011_agent_runs'
branch_labels=None
depends_on=None

def upgrade():
    from alembic import op
    from app.models.studio import StorySource,SourceChapter,ProjectBaseline,ImportedChapter,StudioTask,ReleaseRecord,PrivateMethod,ModelCall,IndexManifest,ChapterFingerprint,SourceIndex
    for model in (StorySource,SourceChapter,ProjectBaseline,ImportedChapter,StudioTask,ReleaseRecord,PrivateMethod,ModelCall,IndexManifest,ChapterFingerprint,SourceIndex):
        model.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():raise RuntimeError('Studio records contain author decisions and sources; use a reviewed retention migration.')
