"""add_webpush_keys

Revision ID: 709ac4ded717
Revises: 023_timeline_filename_tiebreak
Create Date: 2026-06-25 20:47:08.027220

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '709ac4ded717'
down_revision: Union[str, None] = '023_timeline_filename_tiebreak'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('push_registrations', sa.Column('webpush_auth', sa.String(), nullable=True))
    op.add_column('push_registrations', sa.Column('webpush_p256dh', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('push_registrations', 'webpush_p256dh')
    op.drop_column('push_registrations', 'webpush_auth')
