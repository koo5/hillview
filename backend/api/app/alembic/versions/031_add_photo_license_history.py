"""Add photo_license_history table

Append-only record of every licence change on a photo, whoever made it —
including the owner's own, which is why this is not the moderation audit. See
``PhotoLicenseHistory`` for the reasoning. Denormalized with no FK cascades so
it survives deletion of the photo, the owner, or the actor.

Revision ID: 031_photo_license_history
Revises: 030_terrain_overlay
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '031_photo_license_history'
down_revision: Union[str, None] = '030_terrain_overlay'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'photo_license_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('photo_id', sa.String(length=255), nullable=False),
        sa.Column('photo_owner_id', sa.String(), nullable=True),
        sa.Column('photo_owner_username', sa.String(), nullable=True),
        sa.Column('old_license', sa.String(), nullable=True),
        sa.Column('new_license', sa.String(), nullable=True),
        sa.Column('actor_user_id', sa.String(), nullable=False),
        sa.Column('actor_username', sa.String(), nullable=True),
        sa.Column('actor_role', sa.String(), nullable=True),
        sa.Column('actor_was_owner', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_photo_license_history_photo', 'photo_license_history', ['photo_id'])
    op.create_index('idx_photo_license_history_owner', 'photo_license_history', ['photo_owner_id'])
    op.create_index('idx_photo_license_history_actor', 'photo_license_history', ['actor_user_id'])
    op.create_index('idx_photo_license_history_created', 'photo_license_history', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_photo_license_history_created', table_name='photo_license_history')
    op.drop_index('idx_photo_license_history_actor', table_name='photo_license_history')
    op.drop_index('idx_photo_license_history_owner', table_name='photo_license_history')
    op.drop_index('idx_photo_license_history_photo', table_name='photo_license_history')
    op.drop_table('photo_license_history')
