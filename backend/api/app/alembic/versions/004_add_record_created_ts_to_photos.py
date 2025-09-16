"""Add record_created_ts column to photos table

Revision ID: 004_record_created_ts
Revises: 003_remove_filepath_column
Create Date: 2025-09-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision: str = '004_record_created_ts'
down_revision: Union[str, None] = '003_remove_filepath_column'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add record_created_ts column as nullable first
    op.add_column('photos', sa.Column('record_created_ts', sa.DateTime(timezone=True), nullable=True))

    # Set record_created_ts to uploaded_at for existing photos
    op.execute("UPDATE photos SET record_created_ts = uploaded_at WHERE record_created_ts IS NULL")

    # Make the column non-nullable
    op.alter_column('photos', 'record_created_ts', nullable=False)

    # Set default for new rows to be auto-set by database
    op.alter_column('photos', 'record_created_ts', server_default=func.now())


def downgrade() -> None:
    # Remove record_created_ts column
    op.drop_column('photos', 'record_created_ts')