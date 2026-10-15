"""Add photo_analysis_queue — the LLM analyzer's work queue, off the photos table

A row exists only while a photo is NOT done under the analyzer's running
ANALYZER_VERSION: never analysed, leased to an analyzer, backing off after a
failure, or given up on. The analyzer enqueues every completed photo whose
photos.analysis document carries a different analyzer_version (no key = 0), and
a complete run writes the document and deletes the row. "Produced by which
version" therefore lives in the document only, and a version bump re-queues
everything on the analyzer's next sync — which is also why this migration
backfills nothing: existing analyses have no key, read as version 0, and the
analyzer starts at 0.

The analyzer claims a row with FOR UPDATE SKIP LOCKED in a short transaction
and then runs the LLM call with no transaction open. Locking this row rather
than the photo row keeps API writers and DDL on photos from queueing behind a
minutes-long analysis, and the lease in next_retry keeps the analyzer clear of
database.py's idle-in-transaction timeout. See ``PhotoAnalysisQueue`` in
common/models.py and docs/db-session-cancellation.md.

last_attempted_version is the ANALYZER_VERSION of the last claim on the photo
(NULL = queued, never claimed); next_retry only means anything under that
version (a future time = lease or backoff, infinity = given up). What happened
and why is not here; the analyzer's per-md5 JSON files record every attempt.

Revision ID: 036_photo_analysis_queue
Revises: 035_site_state
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '036_photo_analysis_queue'
down_revision: Union[str, None] = '035_site_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'photo_analysis_queue',
        sa.Column('photo_id', sa.String(), nullable=False),
        sa.Column('last_attempted_version', sa.Integer(), nullable=True),
        sa.Column('next_retry', sa.DateTime(timezone=True), server_default=sa.text("'epoch'"), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('photo_id'),
    )


def downgrade() -> None:
    op.drop_table('photo_analysis_queue')
