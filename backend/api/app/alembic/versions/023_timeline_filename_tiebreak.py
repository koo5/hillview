"""Break timeline effective_at ties by original_filename.

The capture-time timeline walk (GET /api/hillview/timeline) orders by
effective_at, but EXIF capture times are only 1-second precise, so burst shots
share a captured_at and tie. We break those ties by original_filename (which
increments with capture order on most cameras/phones) before the final id
tiebreak. COALESCE(original_filename, '') keeps null filenames inside the keyset
walk and lets the ordering use the index. This replaces the
(owner_id, effective_at, id) index from revision 022 with one that carries the
filename key, so the keyset scan stays index-ordered with no sort node.

Revision ID: 023_timeline_filename_tiebreak
Revises: 022_add_effective_at
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = '023_timeline_filename_tiebreak'
down_revision: Union[str, None] = '022_add_effective_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_photos_owner_effective_at_filename_id
        ON photos (owner_id, effective_at, (coalesce(original_filename, '')), id)
    """)
    op.drop_index('ix_photos_owner_effective_at_id', table_name='photos')


def downgrade() -> None:
    op.create_index('ix_photos_owner_effective_at_id', 'photos', ['owner_id', 'effective_at', 'id'])
    op.drop_index('ix_photos_owner_effective_at_filename_id', table_name='photos')
