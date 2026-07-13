"""Add photo_moderation_audit table

Records moderation actions (currently deletions) performed by admins/moderators
on photos they do not own. Denormalized snapshots with no FK cascade deletes so
the audit trail survives later removal of the actor, the owner, or the photo.

Revision ID: 025_photo_moderation_audit
Revises: 024_add_retry_after_minutes
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '025_photo_moderation_audit'
down_revision: Union[str, None] = '024_add_retry_after_minutes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'photo_moderation_audit',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('actor_user_id', sa.String(), nullable=False),
        sa.Column('actor_username', sa.String(), nullable=True),
        sa.Column('actor_role', sa.String(), nullable=True),
        sa.Column('photo_source', sa.String(length=20), server_default='hillview', nullable=False),
        sa.Column('photo_id', sa.String(length=255), nullable=False),
        sa.Column('photo_owner_id', sa.String(), nullable=True),
        sa.Column('photo_owner_username', sa.String(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('extra_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_photo_moderation_audit_action', 'photo_moderation_audit', ['action'])
    op.create_index('idx_photo_moderation_audit_actor', 'photo_moderation_audit', ['actor_user_id'])
    op.create_index('idx_photo_moderation_audit_photo', 'photo_moderation_audit', ['photo_id'])
    op.create_index('idx_photo_moderation_audit_owner', 'photo_moderation_audit', ['photo_owner_id'])
    op.create_index('idx_photo_moderation_audit_created', 'photo_moderation_audit', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_photo_moderation_audit_created', table_name='photo_moderation_audit')
    op.drop_index('idx_photo_moderation_audit_owner', table_name='photo_moderation_audit')
    op.drop_index('idx_photo_moderation_audit_photo', table_name='photo_moderation_audit')
    op.drop_index('idx_photo_moderation_audit_actor', table_name='photo_moderation_audit')
    op.drop_index('idx_photo_moderation_audit_action', table_name='photo_moderation_audit')
    op.drop_table('photo_moderation_audit')
