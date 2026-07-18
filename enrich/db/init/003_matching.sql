-- M3: match evidence. Verdicts (human truth) live in the graph as curated
-- hv:depictedIn facts; match RESULTS (machine measurements: counts, ratios,
-- overlay images) are run-relative evidence and live here, queryable in SQL.

CREATE TABLE IF NOT EXISTS match_results (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  annotation_id text NOT NULL,
  photo_id      text NOT NULL,
  matcher       text NOT NULL DEFAULT 'mast3r',
  params        jsonb NOT NULL DEFAULT '{}',
  status        text NOT NULL DEFAULT 'queued',   -- queued | done | error
  raw_matches   integer,
  inliers       integer,
  ratio         double precision,                 -- inliers / raw
  error         text,
  overlay_path  text,
  worker        text,
  enqueued_at   timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);
CREATE INDEX IF NOT EXISTS ix_match_results_ann ON match_results (annotation_id, enqueued_at DESC);
CREATE INDEX IF NOT EXISTS ix_match_results_status ON match_results (status);
