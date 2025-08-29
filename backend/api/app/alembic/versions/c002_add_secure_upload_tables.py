"""Add secure upload tables and columns

Revision ID: c002_add_secure_upload_tables
Revises: c001_add_security_audit_log
Create Date: 2025-01-29 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c002_add_secure_upload_tables'
down_revision: Union[str, None] = 'c001_add_security_audit_log'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_public_keys table for client ECDSA keys
    op.create_table('user_public_keys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('key_id', sa.String(), nullable=False),
        sa.Column('public_key_pem', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key_id', name='uq_user_public_keys_user_key')
    )
    op.create_index(op.f('ix_user_public_keys_key_id'), 'user_public_keys', ['key_id'], unique=False)
    
    # Add client signature fields to photos table
    op.add_column('photos', sa.Column('client_signature', sa.Text(), nullable=True))
    op.add_column('photos', sa.Column('client_public_key_id', sa.String(), nullable=True))
    op.add_column('photos', sa.Column('upload_authorized_at', sa.DateTime(timezone=True), nullable=True))
    
    # Add worker identity tracking fields to photos table
    op.add_column('photos', sa.Column('processed_by_worker', sa.String(), nullable=True))
    op.add_column('photos', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove worker tracking columns from photos table
    op.drop_column('photos', 'processed_at')
    op.drop_column('photos', 'processed_by_worker')
    
    # Remove client signature columns from photos table
    op.drop_column('photos', 'upload_authorized_at')
    op.drop_column('photos', 'client_public_key_id')
    op.drop_column('photos', 'client_signature')
    
    # Drop user_public_keys table
    op.drop_index(op.f('ix_user_public_keys_key_id'), table_name='user_public_keys')
    op.drop_table('user_public_keys')