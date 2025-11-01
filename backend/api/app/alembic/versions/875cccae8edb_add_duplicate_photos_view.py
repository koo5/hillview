"""Add duplicate_photos view

Revision ID: 875cccae8edb
Revises: d075e1120235
Create Date: 2025-09-28 22:47:31.663785

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '875cccae8edb'
down_revision: Union[str, None] = 'd075e1120235'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create duplicate_photos view using PostGIS geometry extraction
    op.execute("""
        CREATE VIEW duplicate_photos AS
        SELECT ST_Y(photos.geometry) AS latitude,
               ST_X(photos.geometry) AS longitude,
               photos.compass_angle,
               count(*)                            AS duplicate_count,
               array_agg(photos.id)                AS photo_ids,
               array_agg(photos.original_filename) AS filenames
        FROM photos
        WHERE photos.geometry IS NOT NULL
          AND photos.compass_angle IS NOT NULL
        GROUP BY ST_Y(photos.geometry), ST_X(photos.geometry), photos.compass_angle
        HAVING count(*) > 1
        ORDER BY (count(*)) DESC, ST_Y(photos.geometry), ST_X(photos.geometry), photos.compass_angle;
    """)


def downgrade() -> None:
    # Drop duplicate_photos view
    op.execute("DROP VIEW IF EXISTS duplicate_photos;")