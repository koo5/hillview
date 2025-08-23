"""Add error column to photos table

Revision ID: bf1132d69902
Revises: d002_creator_fields
Create Date: 2025-08-23 22:26:33.763739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf1132d69902'
down_revision: Union[str, None] = 'd002_creator_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add error column to photos table
    op.add_column('photos', sa.Column('error', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove error column from photos table
    op.drop_column('photos', 'error')