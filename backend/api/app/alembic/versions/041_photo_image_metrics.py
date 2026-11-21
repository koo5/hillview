"""Add photos.image_metrics: deterministic measurements of the stored image.

The LLM's opinion of a photo lives in photos.analysis, which the analyzer owns
(its analyzer_version stamp drives the re-queue). Numbers computed by code from
the pixels — first sharpness, later perhaps exposure or noise — get their own
column, so neither writer can disturb the other's contract.

One key per metric family, each carrying its own version:
{"sharpness": {"version": 1, ...}}. A writer replaces only its own key.

No index yet: add an expression index when a filter starts reading a value.

Revision ID: 041_photo_image_metrics
Revises: 040_panoramax_photo_status
"""
from alembic import op

revision = '041_photo_image_metrics'
down_revision = '040_panoramax_photo_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.execute("ALTER TABLE photos ADD COLUMN image_metrics JSONB")


def downgrade() -> None:
	op.execute("ALTER TABLE photos DROP COLUMN IF EXISTS image_metrics")
