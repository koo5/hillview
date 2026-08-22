"""Add photos.terrain_overlay — the graduated terrain overlay document

A per-photo horizon line + peak labels, fitted in the enrichment workbench
against a rendered terrain depth panorama and graduated through the usual
hillview-enrichment package (docs/terrain-overlay-graduation.md). The document
is baked to vectors at export time — fit (~200 B) + skyline elevation/distance
per azimuth sample + visible labels + the DEM licence notice — so drawing it
needs no depth buffer, no terrain worker and no artifact store: ~25-50 KB raw,
6-12 KB over the wire, against 117 KB (median) for a gzipped depth buffer.

A column rather than a sidecar table, deliberately:
  * KB-scale JSON on the photos row is established here (detected_objects is
    documented as "KBs per photo", plus exif_data / analysis / geocode), and
    every list endpoint already curates its fields explicitly, so nothing
    existing starts shipping this by accident;
  * the enrichment workbench mirrors hillview COLUMNS, and that mirror is the
    only way it can observe that an overlay landed — a sidecar table would
    need a whole second mirror + reconcile pass to close the same loop.

Served on demand from GET /api/photos/{id}/terrain-overlay (column-scoped
select, like /detections) rather than inlined into any photo response.

Revision ID: 030_terrain_overlay
Revises: 029_share_links
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '030_terrain_overlay'
down_revision: Union[str, None] = '029_share_links'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('terrain_overlay', JSONB, nullable=True))
    # "which photos have an overlay" is the only query shape (the graduation
    # applier and the viewer both address a single row by id), so a partial
    # index on presence is all that earns its keep — no GIN over the document
    op.create_index('ix_photos_terrain_overlay_present', 'photos', ['id'],
                    postgresql_where=sa.text('terrain_overlay IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('ix_photos_terrain_overlay_present', table_name='photos')
    op.drop_column('photos', 'terrain_overlay')
