"""Add photos.blurry: the filterable blur verdict.

Derived by code (common/image_quality.py is_blurry) from
image_metrics->'sharpness', not by a generated column: retuning the rule then
means re-running image_metrics_backfill.py classify, not a migration that
rewrites every row. NULL means not judged — unmeasured (curated wide sources,
uploads the worker has not measured yet) or nothing to judge.

The "not blurry" filter reads `blurry IS NOT TRUE` (most rows: no index
helps). The partial index serves the inverse, the DEV-mode "blurry" view.

Revision ID: 043_photo_blurry
Revises: 042_panoramax_review_fixes
"""
from alembic import op

revision = '043_photo_blurry'
down_revision = '042_panoramax_review_fixes'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.execute("ALTER TABLE photos ADD COLUMN blurry BOOLEAN")
	op.execute("CREATE INDEX ix_photos_blurry ON photos (id) WHERE blurry")


def downgrade() -> None:
	op.execute("DROP INDEX IF EXISTS ix_photos_blurry")
	op.execute("ALTER TABLE photos DROP COLUMN IF EXISTS blurry")
