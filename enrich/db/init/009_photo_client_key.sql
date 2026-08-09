-- Mirror the uploading device's key fingerprint.
--
-- Why: deciding whether a photo cluster came from ONE camera governs whether a single
-- focal length may be solved for the whole cluster (recon's shared_intrinsics), and it is
-- the difference between constraining the lens to what the hardware is and letting the
-- optimizer invent a 119-degree fisheye to absorb error. The app strips camera EXIF from
-- its own uploads, so Make/Model is available for only ~12% of the mirror; the client key
-- is populated for 100% of production rows and is per-device, where owner_id is per-account
-- (one account, several phones).
--
-- Existing mirror rows stay NULL until the next reconcile re-reads them from the source;
-- the camera-identity check falls back to owner + frame dimensions when it is missing.

ALTER TABLE photo_mirror ADD COLUMN IF NOT EXISTS client_public_key_id varchar;

-- cluster selection asks "same device, close in time"
CREATE INDEX IF NOT EXISTS ix_photo_mirror_client_key
  ON photo_mirror (client_public_key_id, captured_at);
