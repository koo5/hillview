"""Two fixes to earlier Panoramax SQL, both found in review.

photo_location_accuracy_m (039) read UserComment in its DECLARE section, and
PL/pgSQL's EXCEPTION clause covers only the block's statements, not its
declarations. exif_data is json, not jsonb, so a UserComment holding a \\u0000
escape (exiftool writes one for a NUL-padded comment) makes ->> raise
"unsupported Unicode escape sequence", and that escaped the function. The
function backs the stored generated column photos.location_accuracy_m, so such
a row could be neither inserted nor updated. The read now happens inside the
block. Stored values are unaffected: every existing row evaluated without
raising, or 039 could not have added the column.

panoramax.bump_sequence_on_photo_change (038) still bumped a sequence when a
member photo's title or description changed. Items serve neither any more, so
each such edit made the harvester re-fetch the whole collection for nothing.

Revision ID: 042_panoramax_review_fixes
Revises: 041_photo_image_metrics
"""
from alembic import op

revision = '042_panoramax_review_fixes'
down_revision = '041_photo_image_metrics'
branch_labels = None
depends_on = None


def accuracy_function(read_in_declare: bool) -> str:
	declare = "uc text := exif->'data'->>'UserComment';" if read_in_declare else 'uc text;'
	read = '' if read_in_declare else "uc := exif->'data'->>'UserComment';"
	return f"""
		CREATE OR REPLACE FUNCTION photo_location_accuracy_m(exif json) RETURNS double precision AS $$
		DECLARE
			{declare}
			metres double precision;
		BEGIN
			{read}
			IF uc IS NULL OR left(uc, 1) <> '{{' THEN
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
	"""


def bump_function(served_text: bool) -> str:
	text_fields = """
				OR OLD.title IS DISTINCT FROM NEW.title
				OR OLD.description IS DISTINCT FROM NEW.description""" if served_text else ''
	return f"""
		CREATE OR REPLACE FUNCTION panoramax.bump_sequence_on_photo_change() RETURNS trigger AS $$
		BEGIN
			IF (OLD.deleted IS DISTINCT FROM NEW.deleted
				OR OLD.is_public IS DISTINCT FROM NEW.is_public
				OR OLD.panoramax_owner_share IS DISTINCT FROM NEW.panoramax_owner_share
				OR OLD.panoramax_moderator_approved IS DISTINCT FROM NEW.panoramax_moderator_approved
				OR OLD.detected_objects::text IS DISTINCT FROM NEW.detected_objects::text
				OR OLD.legal_rights IS DISTINCT FROM NEW.legal_rights
				OR OLD.geometry::text IS DISTINCT FROM NEW.geometry::text
				OR OLD.compass_angle IS DISTINCT FROM NEW.compass_angle
				OR OLD.captured_at IS DISTINCT FROM NEW.captured_at
				OR OLD.effective_at IS DISTINCT FROM NEW.effective_at
				OR OLD.sizes::text IS DISTINCT FROM NEW.sizes::text{text_fields}
				OR OLD.processing_status IS DISTINCT FROM NEW.processing_status) THEN
				UPDATE panoramax.sequences s
				SET updated_at = now()
				FROM panoramax.sequence_photos sp
				WHERE sp.photo_id = NEW.id AND s.id = sp.sequence_id;
			END IF;
			RETURN NULL;
		END;
		$$ LANGUAGE plpgsql;
	"""


def upgrade() -> None:
	op.execute(accuracy_function(read_in_declare=False))
	op.execute(bump_function(served_text=False))


def downgrade() -> None:
	op.execute(bump_function(served_text=True))
	op.execute(accuracy_function(read_in_declare=True))
