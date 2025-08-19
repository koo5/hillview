"""Initial complete setup - PostGIS and full schema

Revision ID: c000_initial_complete_setup
Revises: None
Create Date: 2025-08-19 21:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = 'c000_initial_complete_setup'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable PostGIS extensions for spatial functionality
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")
    
    # 2. Create user role enum with proper exception handling
    try:
        op.execute("DO $$ BEGIN CREATE TYPE userrole AS ENUM ('USER', 'ADMIN', 'MODERATOR'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    except Exception:
        pass  # Type already exists
    
    # 3. Create users table
    op.create_table('users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_test', sa.Boolean(), nullable=False, default=False),
        sa.Column('role', postgresql.ENUM('USER', 'ADMIN', 'MODERATOR', name='userrole', create_type=False), nullable=False, default='USER'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('oauth_provider', sa.String(), nullable=True),
        sa.Column('oauth_id', sa.String(), nullable=True),
        sa.Column('auto_upload_enabled', sa.Boolean(), nullable=True, default=False),
        sa.Column('auto_upload_folder', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    
    # 4. Create photos table  
    op.create_table('photos',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('original_filename', sa.String(), nullable=False),
        sa.Column('filepath', sa.String(), nullable=True),
        sa.Column('thumbnail_path', sa.String(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('altitude', sa.Float(), nullable=True),
        sa.Column('compass_angle', sa.Float(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True, default=True),
        sa.Column('processing_status', sa.String(), nullable=True, default='pending'),
        sa.Column('exif_data', sa.JSON(), nullable=True),
        sa.Column('detected_objects', sa.JSON(), nullable=True),
        sa.Column('sizes', sa.JSON(), nullable=True),
        sa.Column('owner_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 5. Create cached_regions table
    op.create_table('cached_regions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('bbox', geoalchemy2.types.Geometry('POLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_complete', sa.Boolean(), nullable=True, default=False),
        sa.Column('photo_count', sa.Integer(), nullable=True, default=0),
        sa.Column('total_requests', sa.Integer(), nullable=True, default=1),
        sa.Column('last_cursor', sa.String(), nullable=True),
        sa.Column('has_more', sa.Boolean(), nullable=True, default=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 6. Create mapillary_photo_cache table
    op.create_table('mapillary_photo_cache',
        sa.Column('mapillary_id', sa.String(), nullable=False),
        sa.Column('geometry', geoalchemy2.types.Geometry('POINT', srid=4326, from_text='ST_GeomFromEWPT', name='geometry'), nullable=True),
        sa.Column('compass_angle', sa.Float(), nullable=True),
        sa.Column('computed_compass_angle', sa.Float(), nullable=True),
        sa.Column('computed_rotation', sa.Float(), nullable=True),
        sa.Column('computed_altitude', sa.Float(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_pano', sa.Boolean(), nullable=True, default=False),
        sa.Column('thumb_1024_url', sa.String(), nullable=True),
        sa.Column('cached_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('region_id', sa.String(), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['region_id'], ['cached_regions.id'], ),
        sa.PrimaryKeyConstraint('mapillary_id')
    )
    
    # 7. Create token_blacklist table
    op.create_table('token_blacklist',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('blacklisted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_token_blacklist_token'), 'token_blacklist', ['token'], unique=True)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_token_blacklist_token'), table_name='token_blacklist')
    op.drop_table('token_blacklist')
    op.drop_table('mapillary_photo_cache')
    op.drop_table('cached_regions')
    op.drop_table('photos')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS userrole")
    
    # Drop PostGIS extensions (careful with this in production!)
    op.execute("DROP EXTENSION IF EXISTS postgis_topology CASCADE")
    op.execute("DROP EXTENSION IF EXISTS postgis CASCADE")