"""Remove unused thumbnail_path column from photos table

Revision ID: 002_remove_thumbnail_path_column
Revises: 001_initial_schema
Create Date: 2025-09-15 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_remove_thumbnail_path_column'
down_revision: Union[str, None] = 'c0d43de831b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the unused thumbnail_path column from photos table
    op.drop_column('photos', 'thumbnail_path')


def downgrade() -> None:
    # Add back the thumbnail_path column if needed to rollback
    op.add_column('photos', sa.Column('thumbnail_path', sa.String(), nullable=True))