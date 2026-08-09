-- Terrain workstream: synthetic depth-panorama renders from photo viewpoints.
-- Renders are run-relative machine artifacts (depth buffer + preview on disk,
-- meta in jsonb), so they live here in SQL like match_results do; any derived
-- facts (e.g. peak identifications) graduate to the graph as curated facts.

CREATE TABLE IF NOT EXISTS terrain_renders (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  photo_id      text,                             -- NULL for ad-hoc viewpoints
  lat           double precision NOT NULL,
  lon           double precision NOT NULL,
  params        jsonb NOT NULL DEFAULT '{}',      -- render() kwargs subset
  status        text NOT NULL DEFAULT 'queued',   -- queued | done | error
  error         text,
  meta          jsonb,                            -- Panorama.meta() from the worker
  depth_path    text,                             -- ARTIFACTS_DIR-relative
  preview_path  text,
  worker        text,
  enqueued_at   timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);
CREATE INDEX IF NOT EXISTS ix_terrain_renders_photo ON terrain_renders (photo_id, enqueued_at DESC);
CREATE INDEX IF NOT EXISTS ix_terrain_renders_status ON terrain_renders (status);
