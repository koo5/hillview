"""Add user role column

Revision ID: ccbba99388d2
Revises: 
Create Date: 2025-08-15 14:58:50.205305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ccbba99388d2'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Create the UserRole enum type
	user_role_enum = postgresql.ENUM('USER', 'ADMIN', 'MODERATOR', name='userrole')
	user_role_enum.create(op.get_bind())
	
	# Add the role column with default value
	op.add_column('users', sa.Column('role', sa.Enum('USER', 'ADMIN', 'MODERATOR', name='userrole'), server_default='USER', nullable=False))


def downgrade() -> None:
	# Drop the role column
	op.drop_column('users', 'role')
	
	# Drop the UserRole enum type
	user_role_enum = postgresql.ENUM('USER', 'ADMIN', 'MODERATOR', name='userrole')
	user_role_enum.drop(op.get_bind())
