-- Pano→pano annotation transfer: one row per (donor annotation, target photo).
-- Pipeline state (sweep/coarse/refine jobs) is DERIVED from match_results rows
-- carrying params.transfer_id — this table only records the human decision.
CREATE TABLE IF NOT EXISTS transfers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  annotation_id text NOT NULL,
  target_photo_id text NOT NULL,
  status text NOT NULL DEFAULT 'open',   -- open | accepted | rejected
  proposed_rect jsonb,                   -- last accepted/observed best bbox
  accepted_annotation_id text,           -- native annotation minted on accept
  note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (annotation_id, target_photo_id)
);
CREATE INDEX IF NOT EXISTS ix_transfers_target ON transfers (target_photo_id);
