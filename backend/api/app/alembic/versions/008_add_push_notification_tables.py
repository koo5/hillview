"""Add push notification tables

Revision ID: 008_push_notifications
Revises: 007_contact_messages
Create Date: 2025-10-25 12:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008_push_notifications'
down_revision: Union[str, None] = '007_contact_messages'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create push_registrations table
    op.create_table(
        'push_registrations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('client_key_id', sa.String(), nullable=False),
        sa.Column('push_endpoint', sa.Text(), nullable=False),
        sa.Column('distributor_package', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_key_id')
    )

    # Create indexes for push_registrations
    op.create_index('ix_push_registrations_client_key_id', 'push_registrations', ['client_key_id'], unique=True)

    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),  # BIGSERIAL
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('action_data', sa.JSON(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )

    # Create indexes for notifications table
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'created_at'], unique=False,
                   postgresql_where=sa.text('read_at IS NULL'))
    op.create_index('ix_notifications_user_type', 'notifications', ['user_id', 'type', 'created_at'], unique=False)
    op.create_index('ix_notifications_expires_at', 'notifications', ['expires_at'], unique=False,
                   postgresql_where=sa.text('expires_at IS NOT NULL'))


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_notifications_expires_at', table_name='notifications')
    op.drop_index('ix_notifications_user_type', table_name='notifications')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_index('ix_push_registrations_client_key_id', table_name='push_registrations')

    # Drop tables
    op.drop_table('notifications')
    op.drop_table('push_registrations')