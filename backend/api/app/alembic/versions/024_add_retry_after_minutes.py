"""Add photos.retry_after_minutes — the worker's retry hint for a failed processing.

The worker already computes a per-failure retry hint (None = permanent, e.g. a
photo too large to process within the time budget; >0 = transient resource
pressure worth retrying after N minutes). Until now it only reached the *sync*
upload response; the *async* path (browser/app via /upload_async) dropped it, so
those clients saw only the free-text ``error`` and had to guess whether a retry
was worthwhile. This column persists the hint on the photo (mirroring ``error``)
so the status/list/get endpoints can hand it to every client.

Nullable, no default: an unprocessed or successfully-processed photo simply has
NULL here (same as a completed photo having NULL error).

Revision ID: 024_add_retry_after_minutes
Revises: 023_timeline_filename_tiebreak
Create Date: 2026-07-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '024_add_retry_after_minutes'
down_revision: Union[str, None] = '023_timeline_filename_tiebreak'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('retry_after_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('photos', 'retry_after_minutes')
