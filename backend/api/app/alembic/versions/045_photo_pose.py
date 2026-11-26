"""Add photos.roll and photos.bearing_source, for the Panoramax level gates.

roll is a plain column like pitch: both are derived by code
(common/capture_pose.py) from the capture app's stamp, written on processing
and by scripts/pose_backfill.py, and other sources are meant to write better
values later. Both follow GPano: pitch positive up, roll positive when the
horizon is turned counterclockwise in the image, measured from the nearest
quarter turn. This migration only adds the column and documents both; the
backfill rewrites pitch, which until now held the app's positive-down value.
See docs/todo/photo-pose-and-level-gates.md.

bearing_source is generated, the photo_location_accuracy_m pattern from 039:
the stamp's bearing_source string, read defensively out of exif_data's
UserComment so the gates can exempt car mode ('gps-kalman'). Anything that is
not a JSON object with a string there gives NULL. Capped at 128 characters:
the longest label in the 2026-11 data is 73.

Revision ID: 045_photo_pose
Revises: 044_analyzer_batches
"""
from alembic import op

revision = '045_photo_pose'
down_revision = '044_analyzer_batches'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.execute("""
		CREATE OR REPLACE FUNCTION photo_bearing_source(exif json) RETURNS text AS $$
		DECLARE
			uc text;
			source json;
		BEGIN
			-- Assigned here, not in DECLARE: an initializer runs outside the
			-- EXCEPTION block, and ->> raises on a NUL-padded comment (042).
			uc := exif->'data'->>'UserComment';
			IF uc IS NULL OR left(uc, 1) <> '{' THEN
				RETURN NULL;
			END IF;
			source := uc::json->'bearing_source';
			IF source IS NULL OR json_typeof(source) <> 'string' THEN
				RETURN NULL;
			END IF;
			RETURN left(source #>> '{}', 128);
		EXCEPTION WHEN others THEN
			RETURN NULL;
		END;
		$$ LANGUAGE plpgsql IMMUTABLE;
	""")
	op.execute("""
		ALTER TABLE photos ADD COLUMN bearing_source text
		GENERATED ALWAYS AS (photo_bearing_source(exif_data)) STORED
	""")
	op.execute("ALTER TABLE photos ADD COLUMN roll double precision")
	op.execute("""
		COMMENT ON COLUMN photos.pitch IS
		'Degrees above the horizon at the image centre, positive up (GPano PosePitchDegrees). common/capture_pose.py'
	""")
	op.execute("""
		COMMENT ON COLUMN photos.roll IS
		'Horizon lean from the nearest quarter turn, (-45, 45], positive counterclockwise (GPano PoseRollDegrees). common/capture_pose.py'
	""")


def downgrade() -> None:
	op.execute("COMMENT ON COLUMN photos.pitch IS NULL")
	op.drop_column('photos', 'roll')
	op.drop_column('photos', 'bearing_source')
	op.execute("DROP FUNCTION photo_bearing_source(json)")
