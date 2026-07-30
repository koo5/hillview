-- Projected donor rect from the matcher (pano→pano annotation transfer):
-- {method, h_inliers, quad, bbox} normalized to the full target photo.
ALTER TABLE match_results ADD COLUMN IF NOT EXISTS projection jsonb;
