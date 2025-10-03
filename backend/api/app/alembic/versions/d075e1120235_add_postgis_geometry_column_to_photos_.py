"""Add PostGIS geometry column to photos table

Revision ID: d075e1120235
Revises: 007_contact_messages
Create Date: 2025-10-03 21:24:05.620369

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = 'd075e1120235'
down_revision: Union[str, None] = '007_contact_messages'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop views that depend on latitude/longitude columns
    op.execute('DROP VIEW IF EXISTS duplicate_photos')
    op.execute('DROP VIEW IF EXISTS new_view')

    # Add geometry column to photos table
    op.add_column('photos', sa.Column('geometry', Geometry('POINT', srid=4326), nullable=True))

    # Populate geometry column from existing latitude/longitude data
    op.execute("""
        UPDATE photos
        SET geometry = ST_Point(longitude, latitude)
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    # Create spatial index on geometry column
    op.execute('CREATE INDEX IF NOT EXISTS idx_photos_geometry ON photos USING GIST (geometry)')

    # Convert captured_at from timestamptz to timestamp (UTC)
    # First convert all values to UTC, then change the column type
    op.execute("""
        ALTER TABLE photos
        ALTER COLUMN captured_at TYPE timestamp without time zone
        USING captured_at AT TIME ZONE 'UTC'
    """)

    # Create B-tree index on captured_at for time-based sorting (DESC for newest first)
    op.create_index('idx_photos_captured_at', 'photos', ['captured_at'], postgresql_using='btree', postgresql_ops={'captured_at': 'DESC'})

    # Drop the old latitude and longitude columns
    op.drop_column('photos', 'latitude')
    op.drop_column('photos', 'longitude')


def downgrade() -> None:
    # Re-add latitude and longitude columns
    op.add_column('photos', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('photos', sa.Column('longitude', sa.Float(), nullable=True))

    # Populate latitude/longitude from geometry column
    op.execute("""
        UPDATE photos
        SET latitude = ST_Y(geometry), longitude = ST_X(geometry)
        WHERE geometry IS NOT NULL
    """)

    # Remove indexes and geometry column
    op.execute('DROP INDEX IF EXISTS idx_photos_geometry')
    op.drop_index('idx_photos_captured_at', table_name='photos')
    op.drop_column('photos', 'geometry')

    # Convert captured_at back to timestamptz (assume UTC input)
    op.execute("""
        ALTER TABLE photos
        ALTER COLUMN captured_at TYPE timestamp with time zone
        USING captured_at AT TIME ZONE 'UTC'
    """)