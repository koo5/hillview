-- M2: durable cache for external lookups (Nominatim / Wikipedia).
-- Keyed by (kind, query); results are raw provider JSON. Being a cache, rows are
-- replaceable — but in practice lookups are cheap to keep forever (provenance!).

CREATE TABLE IF NOT EXISTS geocode_cache (
  kind       text NOT NULL,          -- 'nominatim' | 'wikipedia'
  query      text NOT NULL,
  result     jsonb,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (kind, query)
);
