"""Add duplicate_photos view

Revision ID: 875cccae8edb
Revises: 006_flagged_photos
Create Date: 2025-09-28 22:47:31.663785

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '875cccae8edb'
down_revision: Union[str, None] = '006_flagged_photos'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create duplicate_photos view
    op.execute("""
        CREATE VIEW duplicate_photos AS
        SELECT photos.latitude,
               photos.longitude,
               photos.compass_angle,
               count(*)                            AS duplicate_count,
               array_agg(photos.id)                AS photo_ids,
               array_agg(photos.original_filename) AS filenames
        FROM photos
        WHERE photos.latitude IS NOT NULL
          AND photos.longitude IS NOT NULL
          AND photos.compass_angle IS NOT NULL
        GROUP BY photos.latitude, photos.longitude, photos.compass_angle
        HAVING count(*) > 1
        ORDER BY (count(*)) DESC, photos.latitude, photos.longitude, photos.compass_angle;
    """)


def downgrade() -> None:
    # Drop duplicate_photos view
    op.execute("DROP VIEW IF EXISTS duplicate_photos;")