"""add photo_annotations table

Revision ID: 013_add_photo_annotations
Revises: d40f1e993188
Create Date: 2026-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013_add_photo_annotations'
down_revision: Union[str, None] = 'd40f1e993188'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'photo_annotations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('photo_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('target', sa.JSON(), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('superseded_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['superseded_by'], ['photo_annotations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_photo_annotations_photo_id', 'photo_annotations', ['photo_id'])


def downgrade() -> None:
    op.drop_index('ix_photo_annotations_photo_id', table_name='photo_annotations')
    op.drop_table('photo_annotations')
