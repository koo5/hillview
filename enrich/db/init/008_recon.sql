-- Recon workstream: MASt3R-SfM reconstructions of photo clusters.
--
-- Machine job rows, like terrain_renders and match_results: the heavy artifacts stay
-- on disk (ARTIFACTS_DIR-relative) and the summary lives in jsonb. Nothing here
-- graduates to the graph — camera poses as RDF facts are a deliberately deferred
-- decision (the two-way-sync machinery needs a rethink first).
--
-- `metrics` holds the recon_metrics.py summary (reprojection + epipolar medians,
-- p90s, coverage, pp/pose provenance) so the bench can list and sort runs without
-- reading the full metrics.json artifact, which carries the per-pair table and can
-- reach a quarter-megabyte.

CREATE TABLE IF NOT EXISTS recon_runs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name           text NOT NULL,                    -- run label, e.g. 'walk_dense'
  source         text NOT NULL DEFAULT 'imported', -- imported (archived dir) | bench
  params         jsonb NOT NULL DEFAULT '{}',      -- reconstruct.py args
  status         text NOT NULL DEFAULT 'queued',   -- queued | running | done | error
  error          text,
  n_frames       integer,
  n_pairs        integer,
  captured_on    date,                             -- capture date of the cluster
  metrics        jsonb,                            -- recon_metrics summary (no per-pair)
  meta           jsonb,                            -- stats/alignment from metadata.json
  metadata_path  text,                             -- ARTIFACTS_DIR-relative
  metrics_path   text,
  cloud_path     text,                             -- points.ply
  topdown_path   text,
  pairs_matrix_path text,
  log_path       text,
  worker         text,
  enqueued_at    timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz
);
-- one row per imported run dir; re-importing updates in place rather than duplicating
CREATE UNIQUE INDEX IF NOT EXISTS ux_recon_runs_name_source ON recon_runs (name, source);
CREATE INDEX IF NOT EXISTS ix_recon_runs_status ON recon_runs (status);
CREATE INDEX IF NOT EXISTS ix_recon_runs_enqueued ON recon_runs (enqueued_at DESC);
