"""Add contact messages table

Revision ID: 007_contact_messages
Revises: 006_flagged_photos
Create Date: 2025-09-29 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '007_contact_messages'
down_revision: Union[str, None] = '006_flagged_photos'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create contact_messages table
    op.create_table(
        'contact_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contact_info', sa.String(500), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),  # Optional - for logged in users
        sa.Column('ip_address', sa.String(45), nullable=True),  # Store IP for spam prevention
        sa.Column('user_agent', sa.String(1000), nullable=True),  # Store user agent for context
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('status', sa.String(20), server_default='new', nullable=False),  # new, read, replied, archived
        sa.Column('admin_notes', sa.Text(), nullable=True),  # For admin use
        sa.Column('replied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replied_by', sa.String(), nullable=True),  # Admin user ID who replied
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['replied_by'], ['users.id'], ondelete='SET NULL'),
    )

    # Create index on created_at for efficient sorting
    op.create_index('ix_contact_messages_created_at', 'contact_messages', ['created_at'], unique=False)

    # Create index on status for filtering
    op.create_index('ix_contact_messages_status', 'contact_messages', ['status'], unique=False)

    # Create index on user_id for user lookup
    op.create_index('ix_contact_messages_user_id', 'contact_messages', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_contact_messages_user_id', table_name='contact_messages')
    op.drop_index('ix_contact_messages_status', table_name='contact_messages')
    op.drop_index('ix_contact_messages_created_at', table_name='contact_messages')

    # Drop table
    op.drop_table('contact_messages')