"""Initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-08-29 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Enable PostGIS extension
	op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
	
	# Create custom enum type (if it doesn't exist)
	op.execute("""
		DO $$ BEGIN
			CREATE TYPE userrole AS ENUM ('USER', 'ADMIN', 'MODERATOR');
		EXCEPTION
			WHEN duplicate_object THEN null;
		END $$;
	""")
	
	# Create users table
	op.create_table('users',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('email', sa.String(), nullable=True),
		sa.Column('username', sa.String(), nullable=True),
		sa.Column('hashed_password', sa.String(), nullable=True),
		sa.Column('is_active', sa.Boolean(), nullable=True),
		sa.Column('is_verified', sa.Boolean(), nullable=True),
		sa.Column('is_test', sa.Boolean(), nullable=False, default=False),
		sa.Column('role', sa.String(), nullable=False, default='USER'),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('oauth_provider', sa.String(), nullable=True),
		sa.Column('oauth_id', sa.String(), nullable=True),
		sa.Column('auto_upload_enabled', sa.Boolean(), nullable=True),
		sa.Column('auto_upload_folder', sa.String(), nullable=True),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index('ix_users_email', 'users', ['email'], unique=True)
	op.create_index('ix_users_username', 'users', ['username'], unique=True)
	
	# Add role constraint manually after enum is created
	op.execute('ALTER TABLE users ADD CONSTRAINT check_user_role CHECK (role IN (\'USER\', \'ADMIN\', \'MODERATOR\'))')
	# Alter column to use enum type
	op.execute('ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole')

	# Create cached_regions table
	op.create_table('cached_regions',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('bbox', Geometry('POLYGON', srid=4326), nullable=True),
		sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('is_complete', sa.Boolean(), nullable=True),
		sa.Column('photo_count', sa.Integer(), nullable=True),
		sa.Column('total_requests', sa.Integer(), nullable=True),
		sa.Column('last_cursor', sa.String(), nullable=True),
		sa.Column('has_more', sa.Boolean(), nullable=True),
		sa.PrimaryKeyConstraint('id')
	)
	op.execute('CREATE INDEX IF NOT EXISTS idx_cached_regions_bbox ON cached_regions USING GIST (bbox)')

	# Create mapillary_photo_cache table
	op.create_table('mapillary_photo_cache',
		sa.Column('mapillary_id', sa.String(), nullable=False),
		sa.Column('geometry', Geometry('POINT', srid=4326), nullable=True),
		sa.Column('compass_angle', sa.Float(), nullable=True),
		sa.Column('computed_compass_angle', sa.Float(), nullable=True),
		sa.Column('computed_rotation', sa.Float(), nullable=True),
		sa.Column('computed_altitude', sa.Float(), nullable=True),
		sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('is_pano', sa.Boolean(), nullable=True),
		sa.Column('thumb_1024_url', sa.String(), nullable=True),
		sa.Column('cached_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('region_id', sa.String(), nullable=True),
		sa.Column('raw_data', sa.JSON(), nullable=True),
		# Creator information
		sa.Column('creator_username', sa.String(255), nullable=True),
		sa.Column('creator_id', sa.String(255), nullable=True),
		sa.ForeignKeyConstraint(['region_id'], ['cached_regions.id']),
		sa.PrimaryKeyConstraint('mapillary_id')
	)
	op.execute('CREATE INDEX IF NOT EXISTS idx_mapillary_photo_cache_geometry ON mapillary_photo_cache USING GIST (geometry)')

	# Create photos table
	op.create_table('photos',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('filename', sa.String(), nullable=True),
		sa.Column('original_filename', sa.String(), nullable=True),
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
		sa.Column('is_public', sa.Boolean(), nullable=True),
		sa.Column('processing_status', sa.String(), nullable=True),
		sa.Column('exif_data', sa.JSON(), nullable=True),
		sa.Column('detected_objects', sa.JSON(), nullable=True),
		sa.Column('sizes', sa.JSON(), nullable=True),
		sa.Column('owner_id', sa.String(), nullable=True),
		# Processing and error tracking
		sa.Column('error', sa.Text(), nullable=True),
		# Secure upload columns  
		sa.Column('client_signature', sa.Text(), nullable=True),
		sa.Column('client_public_key_id', sa.String(), nullable=True),
		sa.Column('upload_authorized_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('processed_by_worker', sa.String(), nullable=True),
		sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
		sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id')
	)

	# Create security_audit_log table
	op.create_table('security_audit_log',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('event_type', sa.String(), nullable=False),
		sa.Column('user_identifier', sa.String(), nullable=True),
		sa.Column('ip_address', sa.String(), nullable=True),
		sa.Column('user_agent', sa.String(), nullable=True),
		sa.Column('event_details', sa.JSON(), nullable=True),
		sa.Column('severity', sa.String(), nullable=False),
		sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('user_id', sa.String(), nullable=True),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index('ix_security_audit_log_event_type', 'security_audit_log', ['event_type'])
	op.create_index('ix_security_audit_log_ip_address', 'security_audit_log', ['ip_address'])
	op.create_index('ix_security_audit_log_timestamp', 'security_audit_log', ['timestamp'])
	op.create_index('ix_security_audit_log_user_identifier', 'security_audit_log', ['user_identifier'])

	# Create token_blacklist table
	op.create_table('token_blacklist',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('token', sa.String(), nullable=False),
		sa.Column('user_id', sa.String(), nullable=False),
		sa.Column('blacklisted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('reason', sa.String(), nullable=True),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index('ix_token_blacklist_token', 'token_blacklist', ['token'], unique=True)

	# Create user_public_keys table
	op.create_table('user_public_keys',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('user_id', sa.String(), nullable=False),
		sa.Column('key_id', sa.String(), nullable=False),
		sa.Column('public_key_pem', sa.Text(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('is_active', sa.Boolean(), nullable=True),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('user_id', 'key_id', name='uq_user_public_keys_user_key')
	)
	op.create_index('ix_user_public_keys_key_id', 'user_public_keys', ['key_id'])

	# Create hidden_photos table
	op.create_table('hidden_photos',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('user_id', sa.String(), nullable=False),
		sa.Column('photo_source', sa.String(20), nullable=False),
		sa.Column('photo_id', sa.String(255), nullable=False),
		sa.Column('hidden_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
		sa.Column('reason', sa.String(100), nullable=True),
		sa.Column('extra_data', sa.JSON(), nullable=True),
		sa.CheckConstraint("photo_source IN ('mapillary', 'hillview')", name='check_photo_source'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('user_id', 'photo_source', 'photo_id', name='unique_user_photo_hide')
	)

	# Create hidden_users table based on model definition
	op.create_table('hidden_users',
		sa.Column('id', sa.String(), nullable=False),
		sa.Column('hiding_user_id', sa.String(), nullable=False),
		sa.Column('target_user_source', sa.String(20), nullable=False),
		sa.Column('target_user_id', sa.String(255), nullable=False),
		sa.Column('hidden_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
		sa.Column('reason', sa.String(100), nullable=True),
		sa.Column('extra_data', sa.JSON(), nullable=True),
		sa.CheckConstraint("target_user_source IN ('mapillary', 'hillview')", name='check_target_user_source'),
		sa.ForeignKeyConstraint(['hiding_user_id'], ['users.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('hiding_user_id', 'target_user_source', 'target_user_id', name='unique_user_target_hide')
	)


def downgrade() -> None:
	# Drop tables in reverse order
	op.drop_table('hidden_users')
	op.drop_table('hidden_photos')
	op.drop_index('ix_user_public_keys_key_id', table_name='user_public_keys')
	op.drop_table('user_public_keys')
	op.drop_index('ix_token_blacklist_token', table_name='token_blacklist')
	op.drop_table('token_blacklist')
	op.drop_index('ix_security_audit_log_user_identifier', table_name='security_audit_log')
	op.drop_index('ix_security_audit_log_timestamp', table_name='security_audit_log')
	op.drop_index('ix_security_audit_log_ip_address', table_name='security_audit_log')
	op.drop_index('ix_security_audit_log_event_type', table_name='security_audit_log')
	op.drop_table('security_audit_log')
	op.drop_table('photos')
	op.drop_table('mapillary_photo_cache')
	op.drop_table('cached_regions')
	op.drop_index('ix_users_username', table_name='users')
	op.drop_index('ix_users_email', table_name='users')
	op.drop_table('users')
	op.execute('DROP TYPE userrole')