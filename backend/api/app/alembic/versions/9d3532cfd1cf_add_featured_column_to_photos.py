"""Add featured column to photos

Revision ID: 9d3532cfd1cf
Revises: 752936a4a4f3
Create Date: 2026-03-18 01:29:50.361824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9d3532cfd1cf'
down_revision: Union[str, None] = '752936a4a4f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('featured', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('photos', 'featured')
