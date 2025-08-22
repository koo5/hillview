"""Add hidden photos and hidden users tables

Revision ID: d001_hidden_content
Revises: c000_initial_complete_setup
Create Date: 2025-08-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd001_hidden_content'
down_revision = '93bf4b05512f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create hidden_photos table
    op.create_table('hidden_photos',
        sa.Column('id', sa.String(), nullable=False, default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('photo_source', sa.String(length=20), nullable=False),
        sa.Column('photo_id', sa.String(length=255), nullable=False),
        sa.Column('hidden_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("photo_source IN ('mapillary', 'hillview')", name='check_photo_source'),
        sa.UniqueConstraint('user_id', 'photo_source', 'photo_id', name='unique_user_photo_hide')
    )
    
    # Create indexes for hidden_photos
    op.create_index('idx_hidden_photos_user_source', 'hidden_photos', ['user_id', 'photo_source'])
    op.create_index('idx_hidden_photos_photo_lookup', 'hidden_photos', ['photo_source', 'photo_id'])
    
    # Create hidden_users table
    op.create_table('hidden_users',
        sa.Column('id', sa.String(), nullable=False, default=sa.text('uuid_generate_v4()')),
        sa.Column('hiding_user_id', sa.String(), nullable=False),
        sa.Column('target_user_source', sa.String(length=20), nullable=False),
        sa.Column('target_user_id', sa.String(length=255), nullable=False),
        sa.Column('hidden_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['hiding_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("target_user_source IN ('mapillary', 'hillview')", name='check_target_user_source'),
        sa.UniqueConstraint('hiding_user_id', 'target_user_source', 'target_user_id', name='unique_user_hide')
    )
    
    # Create indexes for hidden_users
    op.create_index('idx_hidden_users_hiding_user', 'hidden_users', ['hiding_user_id', 'target_user_source'])
    op.create_index('idx_hidden_users_target_lookup', 'hidden_users', ['target_user_source', 'target_user_id'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_hidden_users_target_lookup')
    op.drop_index('idx_hidden_users_hiding_user')
    op.drop_index('idx_hidden_photos_photo_lookup')
    op.drop_index('idx_hidden_photos_user_source')
    
    # Drop tables
    op.drop_table('hidden_users')
    op.drop_table('hidden_photos')