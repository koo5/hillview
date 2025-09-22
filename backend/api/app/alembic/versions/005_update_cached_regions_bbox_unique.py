"""Add uniqueness constraint to bbox column and remove last_cursor from cached_regions

Revision ID: 005_bbox_unique
Revises: 004_record_created_ts
Create Date: 2025-09-22 23:19:28.332436

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005_bbox_unique'
down_revision: Union[str, None] = '004_record_created_ts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the last_cursor column from cached_regions
    op.drop_column('cached_regions', 'last_cursor')

    # Add uniqueness constraint to bbox column
    # Note: This will fail if there are duplicate bbox values in the table
    # In that case, you'll need to clean up duplicates first
    op.create_unique_constraint('uq_cached_regions_bbox', 'cached_regions', ['bbox'])


def downgrade() -> None:
    # Remove the uniqueness constraint on bbox
    op.drop_constraint('uq_cached_regions_bbox', 'cached_regions', type_='unique')

    # Add back the last_cursor column
    op.add_column('cached_regions', sa.Column('last_cursor', sa.String(), nullable=True))