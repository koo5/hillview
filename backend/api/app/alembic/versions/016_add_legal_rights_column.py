"""Add legal_rights column to photos table.

Backfills all existing rows with 'full1' (operator seed content).

Revision ID: 016_add_legal_rights
Revises: 015_normalize_annotation_coords
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '016_add_legal_rights'
down_revision: Union[str, None] = '015_normalize_annotation_coords'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('legal_rights', sa.String(), nullable=True))
    op.execute("UPDATE photos SET legal_rights = 'full1'")


def downgrade() -> None:
    op.drop_column('photos', 'legal_rights')
