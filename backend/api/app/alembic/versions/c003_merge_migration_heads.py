"""Merge migration heads

Revision ID: c003_merge_migration_heads
Revises: c002_add_secure_upload_tables, 93bf4b05512f, bf1132d69902, d001_hidden_content, d002_creator_fields
Create Date: 2025-08-29 07:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c003_merge_migration_heads'
down_revision: Union[str, Sequence[str], None] = [
    'c002_add_secure_upload_tables',
    '93bf4b05512f', 
    'bf1132d69902',
    'd001_hidden_content',
    'd002_creator_fields'
]
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This is a merge migration - no schema changes needed
    pass


def downgrade() -> None:
    # This is a merge migration - no schema changes needed
    pass