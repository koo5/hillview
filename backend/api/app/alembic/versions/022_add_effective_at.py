"""Add photos.effective_at (capture time, else upload time) + index + trigger.

The capture-time timeline walk (GET /api/hillview/timeline) orders by capture
time, falling back to upload time for photos with no EXIF timestamp. Ordering by
COALESCE(captured_at, uploaded_at) at query time can't use an index (the tz cast
isn't IMMUTABLE), so we materialise it into a stored column kept current by a
trigger, and index (owner_id, effective_at, id) for the keyset walk. This
supersedes the (owner_id, captured_at, id) index from revision 021.

Revision ID: 022_add_effective_at
Revises: 021_add_owner_captured_index
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '022_add_effective_at'
down_revision: Union[str, None] = '021_add_owner_captured_index'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('effective_at', sa.DateTime(timezone=False), nullable=True))

    # Keep effective_at = captured_at, else upload time (as naive UTC) current on
    # every insert/update. A trigger (not a GENERATED column) because the tz cast
    # isn't IMMUTABLE, which generated columns require. BEFORE INSERT sees the
    # server_default-applied uploaded_at, so new uploads are covered too.
    op.execute("""
        CREATE OR REPLACE FUNCTION photos_set_effective_at() RETURNS trigger AS $$
        BEGIN
            NEW.effective_at := COALESCE(NEW.captured_at, NEW.uploaded_at AT TIME ZONE 'UTC');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER photos_effective_at_trg
        BEFORE INSERT OR UPDATE ON photos
        FOR EACH ROW EXECUTE FUNCTION photos_set_effective_at();
    """)

    # Backfill existing rows.
    op.execute("UPDATE photos SET effective_at = COALESCE(captured_at, uploaded_at AT TIME ZONE 'UTC')")

    op.create_index('ix_photos_owner_effective_at_id', 'photos', ['owner_id', 'effective_at', 'id'])
    op.drop_index('ix_photos_owner_captured_id', table_name='photos')


def downgrade() -> None:
    op.create_index('ix_photos_owner_captured_id', 'photos', ['owner_id', 'captured_at', 'id'])
    op.drop_index('ix_photos_owner_effective_at_id', table_name='photos')
    op.execute("DROP TRIGGER IF EXISTS photos_effective_at_trg ON photos")
    op.execute("DROP FUNCTION IF EXISTS photos_set_effective_at()")
    op.drop_column('photos', 'effective_at')
