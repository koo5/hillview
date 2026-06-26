-- Backfill captured_at from the capture epoch embedded in phone/screenshot filenames
-- (<localdatetime>_photo_<unixms>_... and ..._capture_<unixms>...). The stamp is the
-- authoritative capture instant in UTC; the leading datetime is just local wall-clock.
-- Only fills rows that have no captured_at; self-contained, prod-portable, idempotent.
-- effective_at is refreshed by the BEFORE UPDATE trigger.
BEGIN;
UPDATE photos
SET captured_at = to_timestamp(
      CASE WHEN n > 4102444800 THEN n / 1000 ELSE n END  -- >2100 in seconds => value is ms
    ) AT TIME ZONE 'UTC'
FROM (SELECT id, (substring(original_filename from '_(?:photo|capture)_([0-9]+)'))::bigint AS n
      FROM photos
      WHERE deleted = false AND captured_at IS NULL
        AND original_filename ~ '_(?:photo|capture)_[0-9]{10,}') s
WHERE photos.id = s.id;
COMMIT;
