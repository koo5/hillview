"""Add creator fields to mapillary_photo_cache

Revision ID: d002_creator_fields
Revises: d001_hidden_content
Create Date: 2025-08-21 12:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd002_creator_fields'
down_revision = 'd001_hidden_content'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add creator fields to mapillary_photo_cache table
    op.add_column('mapillary_photo_cache', sa.Column('creator_username', sa.String(length=255), nullable=True))
    op.add_column('mapillary_photo_cache', sa.Column('creator_id', sa.String(length=255), nullable=True))
    
    # Create indexes for efficient filtering by creator
    op.create_index('idx_mapillary_creator_username', 'mapillary_photo_cache', ['creator_username'])
    op.create_index('idx_mapillary_creator_id', 'mapillary_photo_cache', ['creator_id'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_mapillary_creator_id')
    op.drop_index('idx_mapillary_creator_username')
    
    # Drop columns
    op.drop_column('mapillary_photo_cache', 'creator_id')
    op.drop_column('mapillary_photo_cache', 'creator_username')