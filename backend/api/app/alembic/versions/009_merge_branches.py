"""Merge parallel migration branches

Revision ID: 009_merge_branches
Revises: 4becdf297d3c, 008_push_notifications
Create Date: 2025-10-26 10:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009_merge_branches'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = ('4becdf297d3c', '008_push_notifications')


def upgrade() -> None:
    # This is a merge migration - no schema changes needed
    # Both branches have already applied their changes
    pass


def downgrade() -> None:
    # This is a merge migration - no schema changes to revert
    pass