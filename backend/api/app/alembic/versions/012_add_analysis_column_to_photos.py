"""Add analysis JSONB column to photos table

Revision ID: 012_add_analysis_column
Revises: 011_add_version_column
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '012_add_analysis_column'
down_revision: Union[str, None] = '011_add_version_column'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add analysis column as JSONB for efficient indexing
    op.add_column('photos', sa.Column('analysis', JSONB, nullable=True))

    # Create GIN index for efficient JSONB queries
    op.create_index(
        'ix_photos_analysis_gin',
        'photos',
        ['analysis'],
        postgresql_using='gin'
    )

    # Create specific B-tree indexes for common filter fields
    # These allow efficient queries like: WHERE analysis->>'time_of_day' = 'day'
    op.execute("""
        CREATE INDEX ix_photos_analysis_time_of_day
        ON photos ((analysis->>'time_of_day'))
        WHERE analysis IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX ix_photos_analysis_location_type
        ON photos ((analysis->>'location_type'))
        WHERE analysis IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX ix_photos_analysis_farthest_distance
        ON photos (((analysis->>'farthest_object_distance')::float))
        WHERE analysis IS NOT NULL AND analysis->>'farthest_object_distance' IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_photos_analysis_farthest_distance")
    op.execute("DROP INDEX IF EXISTS ix_photos_analysis_location_type")
    op.execute("DROP INDEX IF EXISTS ix_photos_analysis_time_of_day")
    op.drop_index('ix_photos_analysis_gin', table_name='photos')
    op.drop_column('photos', 'analysis')
