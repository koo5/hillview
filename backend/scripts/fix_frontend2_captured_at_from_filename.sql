-- Reset captured_at of one owner's frontend2 fast-write uploads from the capture
-- epoch in the filename. frontend2 names each capture hillview_photo_<capturedAtMs>.jpg
-- (PhotoCapture.android.kt), so the filename IS the shutter instant in UTC ms.
--
-- Why: the fast-write path writes no EXIF of its own; the file only carries CameraX's
-- DateTimeOriginal, a naive LOCAL wall-clock with no OffsetTimeOriginal. A worker
-- predating "metadata WINS" (9c56e04e) fell back to that and assumed UTC, storing
-- captured_at shifted by the phone's UTC offset (+2h in CEST). The upload metadata's
-- ms-ISO captured_at (buildUploadMetadata) is the same instant as the filename.
--
-- Sibling of backfill_captured_at_from_filename.sql, which only fills NULLs; this one
-- overwrites. Absolute values => idempotent. effective_at is refreshed by the
-- BEFORE UPDATE trigger (migration 022). exif_data is left as recorded (it is the
-- file's EXIF, not the stamp).
--
-- Usage (preview, then apply):
--   psql -v owner=<username> -f fix_frontend2_captured_at_from_filename.sql
-- Nothing is written unless you also pass -v apply=1.

\set ON_ERROR_STOP on
\if :{?owner}
\else
  \echo 'usage: psql -v owner=<username> [-v apply=1] -f fix_frontend2_captured_at_from_filename.sql'
  \quit 1
\endif

-- Candidate rows: this owner's hillview_photo_<ms>.jpg uploads whose stored
-- captured_at is off from the filename instant by more than a second (a correctly
-- stamped row differs only by sub-second truncation).
CREATE TEMP TABLE _fix AS
SELECT p.id, p.original_filename, p.captured_at AS old_captured_at,
       (to_timestamp(s.ms / 1000.0) AT TIME ZONE 'UTC') AS new_captured_at
FROM photos p
JOIN users u ON u.id = p.owner_id
CROSS JOIN LATERAL (
  SELECT (substring(p.original_filename from '^hillview_photo_([0-9]{13})\.jpg$'))::bigint AS ms
) s
WHERE u.username = :'owner'
  AND p.deleted = false
  AND s.ms IS NOT NULL
  AND (p.captured_at IS NULL
       OR abs(extract(epoch from (p.captured_at - (to_timestamp(s.ms / 1000.0) AT TIME ZONE 'UTC')))) > 1);

\echo '--- rows to fix (delta_h = old - new, hours):'
SELECT original_filename, old_captured_at, new_captured_at,
       round((extract(epoch from (old_captured_at - new_captured_at)) / 3600)::numeric, 2) AS delta_h
FROM _fix ORDER BY new_captured_at;
SELECT count(*) AS to_fix FROM _fix;

\if :{?apply}
  BEGIN;
  UPDATE photos SET captured_at = f.new_captured_at
  FROM _fix f WHERE photos.id = f.id;
  COMMIT;
  \echo '--- applied'
\else
  \echo '--- dry run; re-run with -v apply=1 to write'
\endif
