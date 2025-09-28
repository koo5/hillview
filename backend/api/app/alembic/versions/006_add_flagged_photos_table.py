"""Add flagged_photos table

Revision ID: 006_flagged_photos
Revises: 005_bbox_unique
Create Date: 2025-09-28 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '006_flagged_photos'
down_revision: Union[str, None] = '005_bbox_unique'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create flagged_photos table
    op.create_table('flagged_photos',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('flagging_user_id', sa.String(), nullable=True),  # No FK, keep for audit
        sa.Column('photo_source', sa.String(length=20), nullable=False),  # 'mapillary' or 'hillview'
        sa.Column('photo_id', sa.String(length=255), nullable=False),
        sa.Column('flagged_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('extra_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('resolved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create unique constraint to prevent duplicate flags per user per photo
    op.create_unique_constraint(
        'unique_user_photo_flag',
        'flagged_photos',
        ['flagging_user_id', 'photo_source', 'photo_id']
    )

    # Create index for efficient lookups by photo
    op.create_index(
        'idx_flagged_photos_source_photo',
        'flagged_photos',
        ['photo_source', 'photo_id']
    )


def downgrade() -> None:
    # Drop the flagged_photos table and its indexes/constraints
    op.drop_index('idx_flagged_photos_source_photo', table_name='flagged_photos')
    op.drop_constraint('unique_user_photo_flag', 'flagged_photos', type_='unique')
    op.drop_table('flagged_photos')