"""Add original_filename column to photos

Revision ID: 68893ad4af5c
Revises: ccbba99388d2
Create Date: 2025-08-15 21:55:45.694302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '68893ad4af5c'
down_revision: Union[str, None] = 'ccbba99388d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Add original_filename column to photos table
	op.add_column('photos', sa.Column('original_filename', sa.String(), nullable=True))
	
	# Copy existing filename values to original_filename for existing records
	op.execute("UPDATE photos SET original_filename = filename WHERE original_filename IS NULL")
	
	# Make original_filename not null after populating it
	op.alter_column('photos', 'original_filename', nullable=False)


def downgrade() -> None:
	# Drop the original_filename column
	op.drop_column('photos', 'original_filename')
