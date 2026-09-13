-- The DENSE point cloud as its own artifact.
--
-- Until now only points.ply (the sparse anchor cloud) was ever uploaded or imported, so
-- the bench's sparse/dense toggle silently served the same file both ways: cloud_packed
-- looked for a sibling dense.ply that no run had. Every cloud anyone judged was the
-- sparse one, which is spiky by nature — points at anchor pixels only — and that is a
-- large part of why the clouds "made no sense".
ALTER TABLE recon_runs ADD COLUMN IF NOT EXISTS dense_cloud_path text;
