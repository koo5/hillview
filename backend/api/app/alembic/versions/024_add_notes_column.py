"""Add notes column to photos.

Place-oriented notes are stored separately from the longer photo description so
we can eventually give them annotation-like licensing/editing behavior without
overloading the existing description body.

Revision ID: 024_add_notes_column
Revises: 023_timeline_filename_tiebreak
Create Date: 2026-06-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '024_add_notes_column'
down_revision: Union[str, None] = '023_timeline_filename_tiebreak'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('photos', 'notes')
