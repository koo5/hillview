#!/usr/bin/env bash
# Seed the LOCAL DEV hillview Postgres from a prod CSV dump, so the dev stack
# (and the enrichment workbench mirroring it) has realistic data.
# Additive + idempotent: ON CONFLICT DO NOTHING; creates stub users for FKs.
#
#   ./seed_dev_from_dump.sh [/shared/photos_1.csv] [/shared/photo_annotations_1.csv]
set -euo pipefail

PHOTOS_CSV="${1:-/shared/photos_1.csv}"
ANNS_CSV="${2:-/shared/photo_annotations_1.csv}"
PG="psql -h 127.0.0.1 -p ${POSTGRES_HOST_PORT:-5432} -U ${POSTGRES_USER:-hillview} -d ${POSTGRES_DB:-hillview} -v ON_ERROR_STOP=1"
export PGPASSWORD="${POSTGRES_PASSWORD:-hillview}"

echo "== staging =="
$PG <<'SQL'
DROP TABLE IF EXISTS _dump_photos, _dump_anns;
CREATE TABLE _dump_photos (
  id text, filename text, original_filename text, altitude text, compass_angle text,
  width text, height text, captured_at text, uploaded_at text, description text,
  is_public text, processing_status text, exif_data text, detected_objects text,
  sizes text, owner_id text, error text, client_signature text,
  client_public_key_id text, upload_authorized_at text, processed_by_worker text,
  processed_at text, file_md5 text, record_created_ts text, geometry text,
  deleted text, version text, analysis text, featured text, legal_rights text,
  title text, keywords text, geocode text, place_name text, place_slug text,
  -- dump format 2 (2026-07) additions:
  place_parent_name text, place_parent_slug text, effective_at text,
  retry_after_minutes text
);
CREATE TABLE _dump_anns (
  id text, photo_id text, user_id text, body text, target text,
  created_at text, is_current text, superseded_by text, event_type text
);
SQL

echo "== load CSVs =="
# header-driven: dump formats vary (format 2 added place_parent_*, effective_at,
# retry_after_minutes); unlisted staging columns stay NULL for older dumps
PHOTO_HEADER=$(head -1 "$PHOTOS_CSV")
$PG -c "\\copy _dump_photos (${PHOTO_HEADER}) FROM '${PHOTOS_CSV}' CSV HEADER"
# annotation dump column order can differ; read its header first
ANN_HEADER=$(head -1 "$ANNS_CSV")
$PG -c "\\copy _dump_anns (${ANN_HEADER}) FROM '${ANNS_CSV}' CSV HEADER"

echo "== stub users + insert =="
$PG <<'SQL'
-- stub users for FK integrity (dev only)
INSERT INTO users (id, username, is_test, role, is_active)
SELECT DISTINCT u, 'dump-' || left(u, 8), false, 'USER'::userrole, true
FROM (SELECT owner_id AS u FROM _dump_photos WHERE owner_id <> ''
      UNION SELECT user_id FROM _dump_anns WHERE user_id <> '') s
ON CONFLICT (id) DO NOTHING;

INSERT INTO photos (
  id, filename, original_filename, altitude, compass_angle, width, height,
  captured_at, uploaded_at, description, is_public, processing_status,
  exif_data, detected_objects, sizes, owner_id, error, client_signature,
  client_public_key_id, upload_authorized_at, processed_by_worker, processed_at,
  file_md5, record_created_ts, geometry, deleted, version, analysis, featured,
  legal_rights, title, keywords, geocode, place_name, place_slug,
  place_parent_name, place_parent_slug, retry_after_minutes)
SELECT
  id, NULLIF(filename,''), NULLIF(original_filename,''),
  NULLIF(altitude,'')::float8, NULLIF(compass_angle,'')::float8,
  NULLIF(width,'')::int, NULLIF(height,'')::int,
  NULLIF(captured_at,'')::timestamp, NULLIF(uploaded_at,'')::timestamptz,
  NULLIF(description,''), NULLIF(is_public,'')::boolean, NULLIF(processing_status,''),
  NULLIF(exif_data,'')::json, NULLIF(detected_objects,'')::json, NULLIF(sizes,'')::json,
  NULLIF(owner_id,''), NULLIF(error,''), NULLIF(client_signature,''),
  NULLIF(client_public_key_id,''), NULLIF(upload_authorized_at,'')::timestamptz,
  NULLIF(processed_by_worker,''), NULLIF(processed_at,'')::timestamptz,
  NULLIF(file_md5,''), NULLIF(record_created_ts,'')::timestamptz,
  CASE WHEN NULLIF(geometry,'') IS NULL THEN NULL
       WHEN geometry LIKE 'POINT%' THEN ST_SetSRID(ST_GeomFromText(geometry), 4326)
       ELSE ST_SetSRID(geometry::geometry, 4326) END,
  COALESCE(NULLIF(deleted,'')::boolean, false), NULLIF(version,'')::int,
  NULLIF(analysis,'')::jsonb, NULLIF(featured,'')::boolean, NULLIF(legal_rights,''),
  NULLIF(title,''), NULLIF(keywords,'')::text[], NULLIF(geocode,'')::jsonb,
  NULLIF(place_name,''), NULLIF(place_slug,''),
  NULLIF(place_parent_name,''), NULLIF(place_parent_slug,''),
  NULLIF(retry_after_minutes,'')::int
FROM _dump_photos
ON CONFLICT (id) DO NOTHING;

-- annotations: two passes (superseded_by is a self-FK)
INSERT INTO photo_annotations (
  id, photo_id, user_id, body, target, created_at, is_current, event_type)
SELECT id, photo_id, NULLIF(user_id,''), NULLIF(body,''), NULLIF(target,'')::json,
       NULLIF(created_at,'')::timestamptz,
       COALESCE(NULLIF(is_current,'')::boolean, true),
       COALESCE(NULLIF(event_type,''), 'created')
FROM _dump_anns
WHERE photo_id IN (SELECT id FROM photos)
ON CONFLICT (id) DO NOTHING;

UPDATE photo_annotations a
SET superseded_by = d.superseded_by
FROM _dump_anns d
WHERE a.id = d.id AND NULLIF(d.superseded_by,'') IS NOT NULL
  AND EXISTS (SELECT 1 FROM photo_annotations x WHERE x.id = d.superseded_by);

DROP TABLE _dump_photos, _dump_anns;
SQL

echo "== result =="
$PG -c "SELECT 'photos' AS t, count(*) FROM photos UNION ALL SELECT 'annotations', count(*) FROM photo_annotations"
