"""Add is_public index to photos table

Revision ID: 4becdf297d3c
Revises: d075e1120235
Create Date: 2025-10-04 20:28:21.614589

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4becdf297d3c'
down_revision: Union[str, None] = 'd075e1120235'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add index on is_public for efficient filtering of public photos
    op.create_index('idx_photos_is_public', 'photos', ['is_public'])


def downgrade() -> None:
    # Remove is_public index
    op.drop_index('idx_photos_is_public', table_name='photos')