"""Add photos.pitch — camera elevation at the shutter

Bearing says which way the camera faced; this says how far it was tilted,
and the viewer pane needs both to offer "the photo above this one" (see
docs/tauri-viewer-ui-contract.md). Nothing has ever recorded it — not the
clients, not the worker, not this column — so every existing row stays null,
which is exactly what the viewer wants: "no pitch recorded" must be
distinguishable from "level", or legacy photos become candidates for both
up and down at once.

Revision ID: 032_photo_pitch
Revises: 031_photo_license_history
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '032_photo_pitch'
down_revision: Union[str, None] = '031_photo_license_history'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('pitch', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('photos', 'pitch')
