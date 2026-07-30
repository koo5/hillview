"""Add source_annotation_id to photo_annotations

An annotation graduated from the enrichment workbench records the workbench-native
annotation id it came from. This is the provenance link AND the idempotency key for
the graduation create-annotation op: applying the same package twice must not create
a duplicate, and the workbench observes the mirrored copy carrying this id to know a
native annotation has landed.

Revision ID: 028_annotation_source
Revises: 027_user_moderation
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '028_annotation_source'
down_revision: Union[str, None] = '027_user_moderation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photo_annotations',
                  sa.Column('source_annotation_id', sa.String(), nullable=True))
    op.create_index('ix_photo_annotations_source', 'photo_annotations',
                    ['source_annotation_id'], unique=False,
                    postgresql_where=sa.text('source_annotation_id IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('ix_photo_annotations_source', table_name='photo_annotations')
    op.drop_column('photo_annotations', 'source_annotation_id')
