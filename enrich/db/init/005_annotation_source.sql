-- Mirror hillview's photo_annotations.source_annotation_id (graduation provenance).
-- When a workbench-native annotation is graduated, hillview creates a copy carrying
-- this = the native id; once that copy syncs back, the reconcile tier retires the
-- local native row (see sync_reconcile) so it isn't shown twice or re-exported.
ALTER TABLE annotation_mirror
  ADD COLUMN IF NOT EXISTS source_annotation_id text;

CREATE INDEX IF NOT EXISTS ix_annotation_mirror_source
  ON annotation_mirror (source_annotation_id) WHERE source_annotation_id IS NOT NULL;
