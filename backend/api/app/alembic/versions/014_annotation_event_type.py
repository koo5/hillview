"""replace deleted boolean with event_type column on photo_annotations

Revision ID: 014_annotation_event_type
Revises: 013_add_photo_annotations
Create Date: 2026-03-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014_annotation_event_type'
down_revision: Union[str, None] = '013_add_photo_annotations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add event_type column with a safe default
    op.add_column('photo_annotations',
        sa.Column('event_type', sa.String(16), nullable=False, server_default='created'))

    # Migrate existing data: deleted rows become event_type='deleted'
    op.execute("UPDATE photo_annotations SET event_type = 'deleted' WHERE deleted = true")

    # Drop the old deleted column
    op.drop_column('photo_annotations', 'deleted')


def downgrade() -> None:
    # Re-add deleted boolean column
    op.add_column('photo_annotations',
        sa.Column('deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # Migrate event_type back to deleted flag
    op.execute("UPDATE photo_annotations SET deleted = true WHERE event_type = 'deleted'")

    # Drop event_type column
    op.drop_column('photo_annotations', 'event_type')
