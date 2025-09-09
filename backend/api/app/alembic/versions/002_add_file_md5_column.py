"""Add file_md5 column to photos table for duplicate detection

Revision ID: 002_add_file_md5_column
Revises: 001_initial_schema
Create Date: 2025-09-09 08:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_add_file_md5_column'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add file_md5 column to photos table for duplicate detection
    op.add_column('photos', sa.Column('file_md5', sa.String(), nullable=True))
    op.create_index(op.f('ix_photos_file_md5'), 'photos', ['file_md5'], unique=False)


def downgrade() -> None:
    # Remove file_md5 column and its index
    op.drop_index(op.f('ix_photos_file_md5'), table_name='photos')
    op.drop_column('photos', 'file_md5')