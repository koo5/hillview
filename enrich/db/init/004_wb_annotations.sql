-- Workbench-native annotations. The mirror normally only GAINS rows from the
-- hillview source, but the workbench can now ORIGINATE annotations too (drawn on
-- the photo page for triangulation etc.). They live in annotation_mirror so all
-- existing tooling (POI, matching, calibration) sees them with zero changes; an
-- `origin` marker keeps the reconcile tier from stamping them missing (they have
-- no source-side row) and, later, lets graduation push them into hillview.
ALTER TABLE annotation_mirror
  ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'hillview';

CREATE INDEX IF NOT EXISTS ix_annotation_mirror_origin
  ON annotation_mirror (origin) WHERE origin <> 'hillview';
