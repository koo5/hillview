"""Add test column to users

Revision ID: add_test_column_to_users
Revises: 68893ad4af5c
Create Date: 2025-08-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_test_column_to_users'
down_revision: Union[str, None] = '68893ad4af5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Add is_test column to users table
	op.add_column('users', sa.Column('is_test', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
	# Drop the is_test column
	op.drop_column('users', 'is_test')