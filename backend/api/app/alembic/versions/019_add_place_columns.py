"""Add reverse-geocoded place columns to photos.

Foundation for SEO place/area aggregation pages and JSON-LD contentLocation.name
(see docs/todo/seo-place-aggregation-pages.md). Populated by an out-of-band
backfill (scripts/backfill_places.py), not at upload time.

  - ``geocode``    JSONB — raw reverse-geocode result we keep so place_name /
                   place_slug can be re-derived later WITHOUT re-geocoding
                   (geocoding is the expensive part). Stores {address, display_name}.
  - ``place_name`` TEXT  — display label at neighborhood/town granularity
                   (e.g. "Prosek, Praha"). Derived from ``geocode``.
  - ``place_slug`` TEXT  — grouping key for aggregation pages (e.g. "prosek").
                   Indexed.

Revision ID: 019_add_place_columns
Revises: 018_add_title_keywords
Create Date: 2026-06-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '019_add_place_columns'
down_revision: Union[str, None] = '018_add_title_keywords'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('geocode', JSONB(), nullable=True))
    op.add_column('photos', sa.Column('place_name', sa.Text(), nullable=True))
    op.add_column('photos', sa.Column('place_slug', sa.Text(), nullable=True))
    op.create_index('ix_photos_place_slug', 'photos', ['place_slug'])


def downgrade() -> None:
    op.drop_index('ix_photos_place_slug', table_name='photos')
    op.drop_column('photos', 'place_slug')
    op.drop_column('photos', 'place_name')
    op.drop_column('photos', 'geocode')
