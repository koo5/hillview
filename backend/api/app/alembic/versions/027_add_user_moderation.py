"""Add user_moderation table

Audit trail of admin user-management actions (role changes, suspensions,
deletions). Denormalized snapshots with no FK cascade deletes so the record
survives later removal of the actor or the target user.

Revision ID: 027_user_moderation
Revises: 026_annotation_moderation
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '027_user_moderation'
down_revision: Union[str, None] = '026_annotation_moderation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_moderation',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('actor_user_id', sa.String(), nullable=False),
        sa.Column('actor_username', sa.String(), nullable=True),
        sa.Column('actor_role', sa.String(), nullable=True),
        sa.Column('target_user_id', sa.String(), nullable=False),
        sa.Column('target_username', sa.String(), nullable=True),
        sa.Column('old_role', sa.String(), nullable=True),
        sa.Column('new_role', sa.String(), nullable=True),
        sa.Column('old_active', sa.Boolean(), nullable=True),
        sa.Column('new_active', sa.Boolean(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_user_moderation_action', 'user_moderation', ['action'])
    op.create_index('idx_user_moderation_actor', 'user_moderation', ['actor_user_id'])
    op.create_index('idx_user_moderation_target', 'user_moderation', ['target_user_id'])
    op.create_index('idx_user_moderation_created', 'user_moderation', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_user_moderation_created', table_name='user_moderation')
    op.drop_index('idx_user_moderation_target', table_name='user_moderation')
    op.drop_index('idx_user_moderation_actor', table_name='user_moderation')
    op.drop_index('idx_user_moderation_action', table_name='user_moderation')
    op.drop_table('user_moderation')
