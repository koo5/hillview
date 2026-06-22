"""Add composite (owner_id, captured_at, id) index on photos.

Supports the capture-time "timeline walk" feature (GET /api/hillview/timeline):
keyset pagination ordered by (captured_at, id) within one or more owners. The
existing idx_photos_captured_at (captured_at only) can't serve the per-owner
ordered range as efficiently. The id tail makes the keyset tiebreaker
index-only (stable ordering when captured_at ties, e.g. burst shots).

Revision ID: 021_add_owner_captured_index
Revises: 020_add_place_parent
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '021_add_owner_captured_index'
down_revision: Union[str, None] = '020_add_place_parent'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_photos_owner_captured_id',
        'photos',
        ['owner_id', 'captured_at', 'id'],
    )


def downgrade() -> None:
    op.drop_index('ix_photos_owner_captured_id', table_name='photos')
