"""Add photos.content_updated_at: when the photo PAGE last changed, for the sitemap.

The sitemap's per-photo <lastmod> used to be uploaded_at, which is written once
and never moves — so a bulk upload that entered the curated sitemap two years
later, the day it got a title or its first annotation, told crawlers "unchanged
since the upload" at exactly the moment a recrawl was wanted. Google stops
trusting lastmod site-wide once it finds it consistently wrong.

Nothing recorded the moment an owner retitled their own photo (the licence
history covers only licence changes, the moderation audit only non-owner
edits), so the column is maintained by triggers rather than derived at query
time or bumped by application code — which also covers the backfill scripts
that write keywords / place_name with raw SQL:

- BEFORE UPDATE ON photos: any change to a column the /photo/[uid] page shows
  or the sitemap's curation rule reads (title, description, keywords, featured,
  licence, bearing, place) stamps now(). Processing-state / rendition writes
  deliberately do NOT count — the worker rewriting sizes is not a content
  change a crawler should revisit for. (Contrast panoramax_photo_change_trg,
  whose federation contract is wider.)
- AFTER INSERT ON photo_annotations: every annotation event is a new row
  (created / updated / deleted / hidden), so an insert trigger sees them all;
  it stamps the event's own created_at onto the photo.

NULL means "never changed since upload"; the sitemap reads
GREATEST(uploaded_at, content_updated_at). Backfilled from the newest
annotation event per photo, the only content change with a recorded time.

Revision ID: 034_photo_content_updated_at
Revises: 033_add_panoramax_schema
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '034_photo_content_updated_at'
down_revision: Union[str, None] = '033_add_panoramax_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column('photos', sa.Column('content_updated_at', sa.DateTime(timezone=True), nullable=True))

	# Backfill before the triggers exist, so the backfill's own UPDATE doesn't
	# run through them.
	op.execute("""
		UPDATE photos p
		SET content_updated_at = a.latest
		FROM (
			SELECT photo_id, max(created_at) AS latest
			FROM photo_annotations
			GROUP BY photo_id
		) a
		WHERE a.photo_id = p.id AND a.latest > p.uploaded_at
	""")

	op.execute("""
		CREATE FUNCTION photos_stamp_content_updated_at() RETURNS trigger AS $$
		BEGIN
			IF (OLD.title IS DISTINCT FROM NEW.title
				OR OLD.description IS DISTINCT FROM NEW.description
				OR OLD.keywords IS DISTINCT FROM NEW.keywords
				OR OLD.featured IS DISTINCT FROM NEW.featured
				OR OLD.legal_rights IS DISTINCT FROM NEW.legal_rights
				OR OLD.compass_angle IS DISTINCT FROM NEW.compass_angle
				OR OLD.place_name IS DISTINCT FROM NEW.place_name) THEN
				NEW.content_updated_at := now();
			END IF;
			RETURN NEW;
		END;
		$$ LANGUAGE plpgsql;
	""")
	op.execute("""
		CREATE TRIGGER photos_content_updated_at_trg
		BEFORE UPDATE ON photos
		FOR EACH ROW EXECUTE FUNCTION photos_stamp_content_updated_at();
	""")

	op.execute("""
		CREATE FUNCTION photo_annotations_stamp_photo_content() RETURNS trigger AS $$
		BEGIN
			UPDATE photos
			SET content_updated_at = COALESCE(NEW.created_at, now())
			WHERE id = NEW.photo_id;
			RETURN NULL;
		END;
		$$ LANGUAGE plpgsql;
	""")
	op.execute("""
		CREATE TRIGGER photo_annotations_content_trg
		AFTER INSERT ON photo_annotations
		FOR EACH ROW EXECUTE FUNCTION photo_annotations_stamp_photo_content();
	""")


def downgrade() -> None:
	op.execute("DROP TRIGGER IF EXISTS photo_annotations_content_trg ON photo_annotations")
	op.execute("DROP FUNCTION IF EXISTS photo_annotations_stamp_photo_content()")
	op.execute("DROP TRIGGER IF EXISTS photos_content_updated_at_trg ON photos")
	op.execute("DROP FUNCTION IF EXISTS photos_stamp_content_updated_at()")
	op.drop_column('photos', 'content_updated_at')
