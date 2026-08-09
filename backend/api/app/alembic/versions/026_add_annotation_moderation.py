"""Add annotation_moderation table

Records reactive moderation actions (undo/revert) on annotation chains, mirroring
photo_moderation_audit: denormalized snapshots with no FK cascade deletes so the
record survives later removal of the moderator, the subject author, the annotation
rows, or the photo. The optional reason is surfaced to the affected author via a
Notification (linked by notification_id).

Revision ID: 026_annotation_moderation
Revises: 025_photo_moderation_audit
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '026_annotation_moderation'
down_revision: Union[str, None] = '025_photo_moderation_audit'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'annotation_moderation',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('target_event_id', sa.String(), nullable=False),
        sa.Column('result_event_id', sa.String(), nullable=True),
        sa.Column('photo_id', sa.String(length=255), nullable=True),
        sa.Column('moderator_user_id', sa.String(), nullable=False),
        sa.Column('moderator_username', sa.String(), nullable=True),
        sa.Column('moderator_role', sa.String(), nullable=True),
        sa.Column('subject_user_id', sa.String(), nullable=True),
        sa.Column('subject_username', sa.String(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('notification_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_annotation_moderation_action', 'annotation_moderation', ['action'])
    op.create_index('idx_annotation_moderation_target', 'annotation_moderation', ['target_event_id'])
    op.create_index('idx_annotation_moderation_photo', 'annotation_moderation', ['photo_id'])
    op.create_index('idx_annotation_moderation_moderator', 'annotation_moderation', ['moderator_user_id'])
    op.create_index('idx_annotation_moderation_subject', 'annotation_moderation', ['subject_user_id'])
    op.create_index('idx_annotation_moderation_created', 'annotation_moderation', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_annotation_moderation_created', table_name='annotation_moderation')
    op.drop_index('idx_annotation_moderation_subject', table_name='annotation_moderation')
    op.drop_index('idx_annotation_moderation_moderator', table_name='annotation_moderation')
    op.drop_index('idx_annotation_moderation_photo', table_name='annotation_moderation')
    op.drop_index('idx_annotation_moderation_target', table_name='annotation_moderation')
    op.drop_index('idx_annotation_moderation_action', table_name='annotation_moderation')
    op.drop_table('annotation_moderation')
