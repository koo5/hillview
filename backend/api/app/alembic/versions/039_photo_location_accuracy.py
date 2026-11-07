"""Expose the capture fix's horizontal accuracy as a column, for SQL gates.

The radius lives inside the capture app's provenance JSON, a string in
exif_data's UserComment, where a WHERE clause cannot reach it safely: casting
another camera's free text to json raises and would fail the whole query. The
function parses it defensively and the stored generated column keeps the
answer beside the row, so the Panoramax eligibility gate compares a number.

Same reading as _location_accuracy_m in api/app/photo_routes.py (which serves
it, rounded): a JSON object in UserComment, a finite positive
location_accuracy_m, anything else NULL. Photos captured before 2026-09-13
never carried it.

Revision ID: 039_photo_location_accuracy
Revises: 038_panoramax_contribution
"""
from alembic import op

revision = '039_photo_location_accuracy'
down_revision = '038_panoramax_contribution'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.execute("""
		CREATE OR REPLACE FUNCTION photo_location_accuracy_m(exif json) RETURNS double precision AS $$
		DECLARE
			uc text := exif->'data'->>'UserComment';
			metres double precision;
		BEGIN
			IF uc IS NULL OR left(uc, 1) <> '{' THEN
				RETURN NULL;
			END IF;
			metres := (uc::json->>'location_accuracy_m')::double precision;
			-- NaN compares greater than everything in PostgreSQL, so > 0 alone lets it through.
			IF metres IS NULL OR metres <= 0 OR metres = 'NaN' OR metres = 'Infinity' THEN
				RETURN NULL;
			END IF;
			RETURN metres;
		EXCEPTION WHEN others THEN
			RETURN NULL;
		END;
		$$ LANGUAGE plpgsql IMMUTABLE;
	""")
	op.execute("""
		ALTER TABLE photos ADD COLUMN location_accuracy_m double precision
		GENERATED ALWAYS AS (photo_location_accuracy_m(exif_data)) STORED
	""")


def downgrade() -> None:
	op.drop_column('photos', 'location_accuracy_m')
	op.execute("DROP FUNCTION photo_location_accuracy_m(json)")
