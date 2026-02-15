"""Add deleted column to photos table

Revision ID: 010_add_deleted_column
Revises: 36f92ec81625
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010_add_deleted_column'
down_revision: Union[str, None] = '36f92ec81625'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted column with default False
    op.add_column('photos', sa.Column('deleted', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('photos', 'deleted')
