"""Add share_links table for /shared/{slug} short share links

Minted when a user clicks the share button (zoomview, gallery, photo page).
The target is a relative map path constructed server-side and is the row's
identity (unique; minting upserts on it). The public slug is derived as
"{id}-{title-slug}" — the title part recomputed from the current photo title at
each mint and ignored on resolution — so no slug column exists at all.
visit_count is incremented on each resolve. Rows are kept forever so published
links never die; photo_id / created_by are SET NULL on deletion of the
referenced row.

Revision ID: 029_share_links
Revises: 028_annotation_source
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '029_share_links'
down_revision: Union[str, None] = '028_annotation_source'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'share_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('target', sa.Text(), nullable=False),
        sa.Column('photo_uid', sa.String(length=200), nullable=False),
        sa.Column('photo_id', sa.String(), sa.ForeignKey('photos.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('visit_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_share_links_target', 'share_links', ['target'], unique=True)
    op.create_index('ix_share_links_photo_id', 'share_links', ['photo_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_share_links_photo_id', table_name='share_links')
    op.drop_index('ix_share_links_target', table_name='share_links')
    op.drop_table('share_links')
