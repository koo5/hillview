"""Add place_parent_name/place_parent_slug to photos.

Second level of the place hierarchy for SEO aggregation pages: the city/area
hub a leaf place rolls up to (e.g. Prosek and Kobylisy both -> Praha). Derived
from the same stored geocode as place_name/place_slug — populate via
scripts/backfill_places.py --rederive, no re-geocoding.

  - ``place_parent_name`` TEXT  — display label of the hub (e.g. "Praha", "Říčany")
  - ``place_parent_slug`` TEXT  — grouping key for the hub page (e.g. "praha-cz"). Indexed.

Revision ID: 020_add_place_parent
Revises: 019_add_place_columns
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '020_add_place_parent'
down_revision: Union[str, None] = '019_add_place_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('place_parent_name', sa.Text(), nullable=True))
    op.add_column('photos', sa.Column('place_parent_slug', sa.Text(), nullable=True))
    op.create_index('ix_photos_place_parent_slug', 'photos', ['place_parent_slug'])


def downgrade() -> None:
    op.drop_index('ix_photos_place_parent_slug', table_name='photos')
    op.drop_column('photos', 'place_parent_slug')
    op.drop_column('photos', 'place_parent_name')
