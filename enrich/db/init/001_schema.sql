-- Enrichment Workbench schema (M0).
-- Plain idempotent SQL by design: the DB is fully reconstructible (mirrors from the
-- hillview source, runs are dev artifacts). Also executed at API startup, so adding a
-- table here + restart is the M0–M2 migration story. Graduate to Alembic when the
-- schema stabilizes (M2+). Facts live in Oxigraph, not here.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- Mirrors of the hillview source tables (read-only analytics copies).
-- Types match backend/common/models.py: String UUID PKs, POINT 4326,
-- tz-naive captured_at/effective_at vs tz-aware uploaded_at. The source's
-- JSON-vs-JSONB split is collapsed to jsonb here (we only read).
-- Sync discipline (see app/sync.py): the mirror only GAINS information —
--   * append tier inserts new rows (watermark on record_created_ts/created_at)
--   * reconcile tier updates changed rows (row_hash) and stamps missing_since
--     for rows gone from the source; nothing is ever deleted here.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS photo_mirror (
  id                 text PRIMARY KEY,
  owner_id           text,
  filename           text,
  original_filename  text,
  file_md5           text,
  geometry           geometry(Point, 4326),
  altitude           double precision,
  compass_angle      double precision,
  width              integer,
  height             integer,
  captured_at        timestamp,
  uploaded_at        timestamptz,
  effective_at       timestamp,
  record_created_ts  timestamptz,
  title              text,
  description        text,
  place_name         text,
  geocode            jsonb,
  sizes              jsonb,
  exif_data          jsonb,
  analysis           jsonb,
  detected_objects   jsonb,
  processing_status  text,
  is_public          boolean,
  deleted            boolean NOT NULL DEFAULT false,
  version            integer,
  row_hash           text,
  synced_at          timestamptz NOT NULL DEFAULT now(),
  missing_since      timestamptz
);
CREATE INDEX IF NOT EXISTS ix_photo_mirror_geom    ON photo_mirror USING gist (geometry);
CREATE INDEX IF NOT EXISTS ix_photo_mirror_deleted ON photo_mirror (deleted);
CREATE INDEX IF NOT EXISTS ix_photo_mirror_created ON photo_mirror (record_created_ts);
-- pano filter used by the annotations bench (aspect >= 2, either orientation)
CREATE INDEX IF NOT EXISTS ix_photo_mirror_pano ON photo_mirror
  ((greatest(width, height)::float / nullif(least(width, height), 0) >= 2.0))
  WHERE deleted = false;

CREATE TABLE IF NOT EXISTS annotation_mirror (
  id            text PRIMARY KEY,
  photo_id      text NOT NULL,
  user_id       text,
  body          text,
  target        jsonb,
  is_current    boolean NOT NULL DEFAULT true,
  superseded_by text,
  created_at    timestamptz,
  event_type    text,
  row_hash      text,
  synced_at     timestamptz NOT NULL DEFAULT now(),
  missing_since timestamptz
);
CREATE INDEX IF NOT EXISTS ix_annotation_mirror_photo   ON annotation_mirror (photo_id);
CREATE INDEX IF NOT EXISTS ix_annotation_mirror_current ON annotation_mirror (is_current)
  WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_annotation_mirror_created ON annotation_mirror (created_at);

-- ---------------------------------------------------------------------------
-- Runs: every batch operation (sync tiers, parse runs, legacy imports, …).
-- graph_iri cross-references the named graph a parse run wrote in Oxigraph.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS runs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind          text NOT NULL,          -- sync_append | sync_reconcile | annotation_parse | legacy_import | …
  params        jsonb NOT NULL DEFAULT '{}',
  status        text NOT NULL DEFAULT 'running',   -- running | succeeded | failed
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz,
  artifacts_dir text,
  graph_iri     text,
  stats         jsonb,
  error         text,
  note          text
);
CREATE INDEX IF NOT EXISTS ix_runs_kind ON runs (kind, started_at DESC);

-- ---------------------------------------------------------------------------
-- Sync bookkeeping: one row per mirrored table.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sync_state (
  table_name        text PRIMARY KEY,   -- 'photo_mirror' | 'annotation_mirror'
  watermark         timestamptz,        -- append tier high-water mark
  last_append_at    timestamptz,
  last_reconcile_at timestamptz,
  stats             jsonb
);
