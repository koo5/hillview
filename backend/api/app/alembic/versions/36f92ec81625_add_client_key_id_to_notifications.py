"""add_client_key_id_to_notifications

Revision ID: 36f92ec81625
Revises: d40f1e993188
Create Date: 2025-11-15 15:26:05.470519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36f92ec81625'
down_revision: Union[str, None] = 'd40f1e993188'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add client_key_id column to notifications table
    op.add_column('notifications', sa.Column('client_key_id', sa.String(), nullable=True))

    # Make user_id nullable (was previously NOT NULL)
    op.alter_column('notifications', 'user_id', nullable=True)

    # Add foreign key constraint to push_registrations
    op.create_foreign_key(
        'fk_notifications_client_key_id',
        'notifications',
        'push_registrations',
        ['client_key_id'],
        ['client_key_id'],
        ondelete='CASCADE'
    )

    # Add indexes for efficient querying
    op.create_index('ix_notifications_client_key_id', 'notifications', ['client_key_id'])
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])

    # Add check constraint to ensure exactly one of user_id or client_key_id is provided
    op.create_check_constraint(
        'notifications_user_or_key_check',
        'notifications',
        '(user_id IS NOT NULL AND client_key_id IS NULL) OR (user_id IS NULL AND client_key_id IS NOT NULL)'
    )


def downgrade() -> None:
    # Remove check constraint
    op.drop_constraint('notifications_user_or_key_check', 'notifications', type_='check')

    # Remove indexes
    op.drop_index('ix_notifications_client_key_id', 'notifications')
    op.drop_index('ix_notifications_user_id', 'notifications')

    # Remove foreign key constraint
    op.drop_constraint('fk_notifications_client_key_id', 'notifications', type_='foreignkey')

    # Make user_id NOT NULL again
    op.alter_column('notifications', 'user_id', nullable=False)

    # Remove client_key_id column
    op.drop_column('notifications', 'client_key_id')