"""Remove filepath column from photos table

Revision ID: 003_remove_filepath_column
Revises: 002_remove_thumbnail_path_column
Create Date: 2025-09-15 11:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003_remove_filepath_column'
down_revision: Union[str, None] = '002_remove_thumbnail_path_column'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the filepath column from photos table
    op.drop_column('photos', 'filepath')


def downgrade() -> None:
    # Add back the filepath column if needed to rollback
    op.add_column('photos', sa.Column('filepath', sa.String(), nullable=True))