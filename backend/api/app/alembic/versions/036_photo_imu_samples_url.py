"""Add photos.imu_samples_url: the raw inertial window stored beside a photo.

The capture app records accelerometer and gyroscope samples around every
exposure — a ±3 s window at whatever rate the phone's sensors run, a few
thousand rows. Until now only the SUMMARY reached the server, folded into the
UserComment provenance as `motion.imu_window` (peak acceleration, peak angular
rate, the bounds). The samples themselves stopped at the device, reachable only
as a tracking CSV pulled off the phone by hand.

They matter because a single sample cannot describe an EXPOSURE: motion blur is
the integral of movement while the shutter is open, rolling shutter smears
differently down the frame, and telling a hand-held wobble from a moving vehicle
needs the SHAPE of the signal rather than one number from the middle of it.

A URL column and not a JSONB payload, deliberately. `photos` is read on every
map bounds query; a window is tens of kilobytes; and `exif_data` — where the
provenance lives — is loaded wholesale on every photo detail request. So the
worker gzips the payload into the same storage pool that holds the photo's
renditions and DZI tiles, and the row keeps only where it went.

NOTE FOR WHOEVER ADDS THE NEXT ARTIFACT COLUMN: the delete path resolves a
storage pool per stored URL. A column it does not know about is a permanent leak
of one file per deleted photo. This one is wired in via
`photos.py::_PHOTO_ARTIFACT_URL_COLUMNS` — add yours there in the same commit.

See docs/recon-capture-metadata.md, Phase 5.

Revision ID: 036_photo_imu_samples_url
Revises: 035_site_state
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '036_photo_imu_samples_url'
down_revision: Union[str, None] = '035_site_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Nullable with no default: every existing row predates the capture of any
	# window, and NULL says exactly that. No backfill is possible — the samples
	# were never uploaded.
	op.add_column('photos', sa.Column('imu_samples_url', sa.Text(), nullable=True))


def downgrade() -> None:
	# Dropping the column orphans whatever files it pointed at; they are
	# harmless (nothing serves them) but they are not reclaimed. A downgrade that
	# also swept them would need the storage pools, which alembic has no business
	# knowing about.
	op.drop_column('photos', 'imu_samples_url')
