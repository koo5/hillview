"""Add version column to photos table for re-upload support

Revision ID: 011_add_version_column
Revises: 010_add_deleted_column
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '011_add_version_column'
down_revision: Union[str, None] = '010_add_deleted_column'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add version column with default 1
    op.add_column('photos', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('photos', 'version')
