#!/usr/bin/env bash
# Seed the LOCAL DEV hillview Postgres from a prod CSV dump, so the dev stack
# (and the enrichment workbench mirroring it) has realistic data.
# Creates stub users for FKs.
#
#   ./seed_dev_from_dump.sh [--additive] /shared/photos_5.csv /shared/photo_annotations_5.csv
#
# Default is a FRESH RELOAD: photos + annotations are truncated and rebuilt from the
# dump, so the dump is authoritative for every column. This is not paranoia about
# duplicates — photo rows MUTATE IN PLACE in prod (analysis, geocode, place_*, title,
# deleted), and an insert-only load can never catch that. Worse, the staleness is
# invisible downstream: the workbench mirror reconciles against THIS db, so both sides
# agree on the stale value and nothing ever flags it.
#
# --additive keeps the old insert-only behaviour (ON CONFLICT DO NOTHING). Use it when
# the dev db holds rows that exist nowhere else — notably annotations GRADUATED from
# the workbench, which a truncate would destroy along with the round-trip they close.
# The fresh path counts those and prints them before touching anything.
#
# Fresh mode SNAPSHOTS BEFORE IT DESTROYS: the mirror only protects rows a sync has
# SEEN (Aug 2026: a 12-day sync gap meant 103 locally-created annotations were
# truncated without a trace), so a workbench reconcile runs before the truncate, and
# the post-reload sync then stamps whatever did not come back (missing_since — never
# deleted). Every workbench read filters stamped rows out, so test junk swept up this
# way is invisible dead weight, not pollution; the hygiene report at the end says
# what accumulated and which of it is purgeable. --no-presync skips the snapshot
# (and its workbench-must-be-up requirement) — that re-opens the blind spot, so
# prefer starting the workbench instead.
#
# The truncate and the reload run in ONE transaction: a concurrent workbench reconcile
# must never observe an empty source, or it would stamp every mirror row missing_since.
set -euo pipefail

MODE=fresh
PRESYNC=yes
ARGS=()
for a in "$@"; do
  case "$a" in
    --additive)   MODE=additive ;;
    --fresh)      MODE=fresh ;;
    --no-presync) PRESYNC=no ;;
    -*) echo "unknown flag: $a" >&2; exit 2 ;;
    *)  ARGS+=("$a") ;;
  esac
done
if [ "${#ARGS[@]}" -lt 2 ]; then
  # no defaults on purpose: the fresh path is destructive, and a default pointing at
  # whichever dump was newest when this was written is exactly the wrong footgun
  echo "usage: $0 [--additive] [--no-presync] <photos.csv> <photo_annotations.csv>" >&2
  exit 2
fi
PHOTOS_CSV="${ARGS[0]}"
ANNS_CSV="${ARGS[1]}"
PG="psql -h 127.0.0.1 -p ${POSTGRES_HOST_PORT:-5432} -U ${POSTGRES_USER:-hillview} -d ${POSTGRES_DB:-hillview} -v ON_ERROR_STOP=1"
export PGPASSWORD="${POSTGRES_PASSWORD:-hillview}"
ENRICH_API="${ENRICH_API:-http://localhost:8070}"

# Trigger one workbench sync pass and wait it out; prints "status stats", succeeds
# only if the run did. A pass is a full reconcile: row-hash compare against the
# source, upsert new/changed rows into the mirror, stamp missing_since on rows gone
# from the source (never delete), clear it on reappearance, retire natives whose
# graduated copy is observed. The run is a background task server-side, so poll the
# status and report where it landed rather than just claiming it started.
run_sync() {
  curl -sf -X POST "$ENRICH_API/api/sync/run" \
       -H 'Content-Type: application/json' -d '{}' >/dev/null || return 1
  local st="" line
  for _ in $(seq 1 200); do
    sleep 3
    st=$(curl -s "$ENRICH_API/api/sync/status")
    case "$st" in *'"running":false'*) break ;; esac
  done
  line=$(echo "$st" | python3 -c 'import json,sys; r=json.load(sys.stdin)["last_runs"][0]; print(r["status"], json.dumps(r["stats"]))') || return 1
  echo "$line"
  case "$line" in succeeded*) return 0 ;; *) return 1 ;; esac
}

if [ "$MODE" = fresh ] && [ "$PRESYNC" = yes ]; then
  echo "== pre-truncate mirror snapshot =="
  run_sync || {
    echo "!! workbench sync failed or unreachable — refusing to truncate blind." >&2
    echo "   The mirror is the only safety net for local-only rows; start the" >&2
    echo "   workbench, or pass --no-presync to accept the blind spot." >&2
    exit 1
  }
fi

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
  retry_after_minutes text,
  -- dump format 3 (2026-08) additions:
  terrain_overlay text, pitch text
);
CREATE TABLE _dump_anns (
  id text, photo_id text, user_id text, body text, target text,
  created_at text, is_current text, superseded_by text, event_type text,
  -- annotation dump format 2 (2026-08): graduation provenance link
  source_annotation_id text
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

if [ "$MODE" = fresh ]; then
  echo "== fresh reload: what the truncate destroys =="
  $PG <<'SQL'
SELECT 'photos not in this dump' AS what, count(*) FROM photos p
 WHERE NOT EXISTS (SELECT 1 FROM _dump_photos d WHERE d.id = p.id)
UNION ALL
SELECT 'annotations not in this dump', count(*) FROM photo_annotations a
 WHERE NOT EXISTS (SELECT 1 FROM _dump_anns d WHERE d.id = a.id)
UNION ALL
SELECT '  ...of which graduated from the workbench', count(*) FROM photo_annotations a
 WHERE a.source_annotation_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM _dump_anns d WHERE d.id = a.id)
UNION ALL
SELECT 'share_links (FK dependent, goes with the photos)', count(*) FROM share_links;
SQL
fi

echo "== stub users + insert (${MODE}) =="
{
  # named explicitly rather than leaning on CASCADE alone, so the script says out loud
  # what it clears; CASCADE only covers FK dependents added later
  [ "$MODE" = fresh ] && printf 'TRUNCATE photo_annotations, share_links, photos CASCADE;\n'
  cat <<'SQL'
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
  place_parent_name, place_parent_slug, retry_after_minutes,
  terrain_overlay, pitch)
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
  -- effective_at is deliberately NOT loaded even though the dump carries it (fully
  -- populated) and the mirror mirrors it: migration 022 keeps it current with a
  -- BEFORE INSERT OR UPDATE trigger, COALESCE(captured_at, uploaded_at AT TIME ZONE
  -- 'UTC'), which overwrites anything we supply. Both inputs ARE loaded here, so the
  -- trigger reproduces prod's value exactly (verified: 0 rows deviate).
  NULLIF(retry_after_minutes,'')::int,
  NULLIF(terrain_overlay,'')::jsonb, NULLIF(pitch,'')::float8
FROM _dump_photos
ON CONFLICT (id) DO NOTHING;

-- annotations: two passes (superseded_by is a self-FK)
INSERT INTO photo_annotations (
  id, photo_id, user_id, body, target, created_at, is_current, event_type,
  source_annotation_id)
SELECT id, photo_id, NULLIF(user_id,''), NULLIF(body,''), NULLIF(target,'')::json,
       NULLIF(created_at,'')::timestamptz,
       COALESCE(NULLIF(is_current,'')::boolean, true),
       COALESCE(NULLIF(event_type,''), 'created'),
       NULLIF(source_annotation_id,'')
FROM _dump_anns
WHERE photo_id IN (SELECT id FROM photos)
ON CONFLICT (id) DO NOTHING;

UPDATE photo_annotations a
SET superseded_by = d.superseded_by
FROM _dump_anns d
WHERE a.id = d.id AND NULLIF(d.superseded_by,'') IS NOT NULL
  AND EXISTS (SELECT 1 FROM photo_annotations x WHERE x.id = d.superseded_by);

-- versioning mutates in prod (supersede flips is_current off on the old row);
-- carry it, else old+new versions are both "current" here and in the mirror
UPDATE photo_annotations a
SET is_current = NULLIF(d.is_current,'')::boolean
FROM _dump_anns d
WHERE a.id = d.id AND NULLIF(d.is_current,'') IS NOT NULL
  AND a.is_current IS DISTINCT FROM NULLIF(d.is_current,'')::boolean;

DROP TABLE _dump_photos, _dump_anns;
SQL
} | $PG --single-transaction

echo "== result =="
$PG -c "SELECT 'photos' AS t, count(*) FROM photos UNION ALL SELECT 'annotations', count(*) FROM photo_annotations"

echo "== mirror into the workbench =="
if run_sync; then
  echo "== stamped-missing hygiene report =="
  # Everything the workbench reads filters missing_since IS NULL, so stamped rows
  # are invisible dead weight — EXCEPT that an UNCLASSIFIED one may be real
  # local-only work the mirror is the last copy of. Test-user junk is safe to
  # purge by hand (in the workbench db, port ${WB_POSTGRES_HOST_PORT:-15432}).
  # The users table survives reseeds, so old test-user ids still classify here.
  test_ids=$($PG -Atc "SELECT COALESCE(string_agg(quote_literal(id), ','), 'NULL')
                       FROM users WHERE is_test OR username IN ('test','admin','testuser')")
  PGPASSWORD="${WB_POSTGRES_PASSWORD:-enrich}" \
  psql -h 127.0.0.1 -p "${WB_POSTGRES_HOST_PORT:-15432}" -U "${WB_POSTGRES_USER:-enrich}" \
       -d "${WB_POSTGRES_DB:-enrich}" -v ON_ERROR_STOP=1 <<SQL
SELECT CASE
    WHEN source_annotation_id IS NOT NULL
      THEN 'graduation rehearsals (same content landed in prod)'
    WHEN user_id IN ($test_ids)
      THEN 'test-user annotations (junk; purgeable by hand)'
    ELSE 'UNCLASSIFIED - possibly real local-only work, review before purging'
  END AS stamped_missing_annotations,
  count(*), max(missing_since)::date AS newest
FROM annotation_mirror
WHERE origin = 'hillview' AND missing_since IS NOT NULL
GROUP BY 1 ORDER BY 1;
SELECT count(*) AS stamped_missing_photos FROM photo_mirror WHERE missing_since IS NOT NULL;
SQL
else
  echo "!! workbench api unreachable — mirror NOT updated. Run this when it is up:" >&2
  echo "   curl -X POST ${ENRICH_API}/api/sync/run -H 'Content-Type: application/json' -d '{}'" >&2
fi
