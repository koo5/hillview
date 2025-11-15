"""merge_notification_heads

Revision ID: 60a7e8902255
Revises: 008_push_notifications, 4becdf297d3c
Create Date: 2025-11-15 15:22:06.234481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60a7e8902255'
down_revision: Union[str, None] = ('008_push_notifications', '4becdf297d3c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass