#!/bin/bash
# End-to-end federation test: drive the REAL Panoramax meta-catalog harvester
# against this repo's panoramax container and assert that every contract the
# federation depends on actually holds.
#
#   ./backend/panoramax/scripts/e2e_federation.sh              # full run
#   ./backend/panoramax/scripts/e2e_federation.sh --no-seed    # use existing photos
#   ./backend/panoramax/scripts/e2e_federation.sh --keep-up    # don't stop the catalog after
#   ./backend/panoramax/scripts/e2e_federation.sh --down       # tear the catalog down and exit
#
# What it exercises, in order:
#   1. hillview stack up (postgres+api+worker+panoramax), migration applied,
#      panoramax_ro provisioned
#   2. seeds CC-licensed photos through the real upload path, laid out as N
#      time-gap sessions -> asserts the sequencer produces exactly N sequences
#   3. meta-catalog stack up, harvester installed, instance registered
#   4. full harvest: asserts collections + items land with ZERO harvest errors
#      (a single bad datetime format silently zeroes the whole import)
#   5. photo edit -> incremental harvest re-fetches exactly that collection
#   6. soft-delete -> sequencer prune -> incremental harvest moves the item to
#      deleted_items; emptying a sequence tombstones it and the tombstone stays
#      listable via the CQL status filter
#   7. restore -> everything comes back
#   8. pystac validation of a served collection + item
#
# Requires: the meta-catalog checked out at $META_CATALOG (default below), uv,
# docker. Leaves the hillview stack running; stops the catalog stack unless
# --keep-up.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f -- "$0")")/../../.." && pwd)"
META_CATALOG="${META_CATALOG:-/home/koom/repos/panoramax/server/meta-catalog/0/meta-catalog}"
WORK_DIR="${WORK_DIR:-${TMPDIR:-/tmp}/panoramax-e2e}"
CATALOG_DB='postgresql://username:password@localhost:5439/panoramax'
INSTANCE_NAME="${INSTANCE_NAME:-hillview-e2e}"
PANORAMAX_URL="${PANORAMAX_URL:-http://localhost:8058}"
SESSIONS="${SESSIONS:-3}"
PER_SESSION="${PER_SESSION:-4}"

SEED=1
KEEP_UP=0
for arg in "$@"; do
	case "$arg" in
		--no-seed) SEED=0 ;;
		--keep-up) KEEP_UP=1 ;;
		--down) docker compose -f "$META_CATALOG/docker-compose.yml" down; exit 0 ;;
		*) echo "unknown option: $arg" >&2; exit 2 ;;
	esac
done

RED=$'\e[31m'; GREEN=$'\e[32m'; BOLD=$'\e[1m'; RESET=$'\e[0m'
step() { echo; echo "${BOLD}==> $*${RESET}"; }
ok()   { echo "${GREEN}  ✓ $*${RESET}"; }
fail() { echo "${RED}  ✗ $*${RESET}" >&2; exit 1; }

assert_eq() {  # assert_eq <actual> <expected> <what>
	[ "$1" = "$2" ] && ok "$3 = $1" || fail "$3: expected $2, got $1"
}

hv_psql()  { docker exec hillview_postgres psql -U "${POSTGRES_USER:-hillview}" -d "${POSTGRES_DB:-hillview}" -tA -c "$1"; }
cat_psql() { docker exec meta-catalog-database-1 psql -U username -d panoramax -tA -c "$1"; }
harvester() { "$WORK_DIR/venv/bin/stac-harvester" "$@" --db "$CATALOG_DB"; }
sequencer() { docker exec hillview_panoramax python /app/app/sequencer.py --once 2>&1 | tail -1; }

# Collections whose harvest failed. This is the check that matters most: the
# harvester logs errors per collection and still reports "imported", so a
# schema mismatch looks like success until you count the errors.
harvest_errors_since() { cat_psql "SELECT count(*) FROM harvest_errors he JOIN harvests h ON h.id = he.harvest_id WHERE h.start > now() - interval '$1'"; }

cd "$REPO_ROOT"
[ -f .env ] || fail ".env missing — copy one in before running (see .env.example)"
set -a; . ./.env; set +a
[ -n "${PANORAMAX_DB_PASSWORD:-}" ] || fail "PANORAMAX_DB_PASSWORD unset in .env"
[ -d "$META_CATALOG" ] || fail "meta-catalog not found at $META_CATALOG (set META_CATALOG=)"

step "1/8  hillview stack"
./compose.sh --profile panoramax up --build -d postgres api worker panoramax >/dev/null
until curl -sf "$PANORAMAX_URL/api/health" >/dev/null 2>&1; do sleep 2; done
ok "panoramax API healthy at $PANORAMAX_URL"
[ "$(hv_psql "SELECT count(*) FROM alembic_version WHERE version_num = '030_add_panoramax_schema'")" = "1" ] \
	|| fail "migration 030 not applied (api prestart should have done it)"
ok "migration 030 applied"
./backend/scripts/provision_panoramax_role.sh >/dev/null 2>&1 && ok "panoramax_ro provisioned"
until curl -sf "http://localhost:8055/api/debug" >/dev/null 2>&1; do sleep 2; done
ok "hillview api reachable"

if [ "$SEED" = "1" ]; then
	step "2/8  seed $SESSIONS sessions × $PER_SESSION photos through the real upload path"
	mkdir -p "$WORK_DIR"
	(cd backend && uv run --quiet --frozen --package hillview-tests \
		python panoramax/scripts/seed_photos.py \
			--sessions "$SESSIONS" --per-session "$PER_SESSION" \
			--out "$WORK_DIR/photo_ids.txt")
	SEEDED_USER=$(hv_psql "SELECT owner_id FROM photos WHERE id = '$(head -1 "$WORK_DIR/photo_ids.txt")'")
	# The seeder uploads as the debug test user, but eligibility deliberately
	# excludes users.is_test (we don't federate test accounts). Clear the flag
	# on the seeded user so the rest of the run exercises the real path —
	# `./backend/debug.sh recreate` restores it.
	hv_psql "UPDATE users SET is_test = false WHERE id = '$SEEDED_USER'" >/dev/null
	ok "seeded user $SEEDED_USER un-flagged as test (eligibility excludes is_test)"
	sequencer
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE owner_id = '$SEEDED_USER' AND status = 'ready'")" \
		"$SESSIONS" "sequences synthesized for the seeded user"
else
	step "2/8  seeding skipped (--no-seed)"
	sequencer
fi

TOTAL_SEQ=$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE status = 'ready'")
TOTAL_PHOTOS=$(hv_psql "SELECT count(*) FROM panoramax.sequence_photos")
ok "$TOTAL_SEQ ready sequences / $TOTAL_PHOTOS memberships"

step "3/8  meta-catalog stack + harvester"
docker compose -f "$META_CATALOG/docker-compose.yml" up -d database migrations >/dev/null 2>&1
until docker exec meta-catalog-database-1 pg_isready -U username -d panoramax >/dev/null 2>&1; do sleep 2; done
until [ "$(cat_psql "SELECT to_regclass('public.instances') IS NOT NULL")" = "t" ]; do sleep 2; done
ok "catalog database migrated"
if [ ! -x "$WORK_DIR/venv/bin/stac-harvester" ]; then
	mkdir -p "$WORK_DIR"
	uv venv "$WORK_DIR/venv" --quiet
	VIRTUAL_ENV="$WORK_DIR/venv" uv pip install --quiet -e "$META_CATALOG/harvester" 'pystac[validation]'
fi
ok "harvester CLI ready"

# Re-register from scratch so each run is independent of catalog leftovers
cat_psql "DELETE FROM instances WHERE name = '$INSTANCE_NAME'" >/dev/null
harvester add-instance "$INSTANCE_NAME" --url "$PANORAMAX_URL" 2>&1 | grep -q "added with id" \
	&& ok "instance registered (configuration endpoint accepted)" \
	|| fail "add-instance failed — /api/configuration is mandatory, check it returns 200"

step "4/8  full harvest"
harvester harvest "$INSTANCE_NAME" --full-harvest 2>&1 | grep -E "🎉|Collections imported: [0-9]+ col \[0" | tail -1
assert_eq "$(harvest_errors_since '5 minutes')" "0" "harvest errors"
assert_eq "$(cat_psql "SELECT count(*) FROM collections")" "$TOTAL_SEQ" "collections in catalog"
assert_eq "$(cat_psql "SELECT count(*) FROM items")" "$TOTAL_PHOTOS" "items in catalog"
[ "$(cat_psql "SELECT count(*) FROM providers")" -gt 0 ] && ok "providers derived" || fail "no providers — providers[*].id/name missing?"
[ "$(cat_psql "SELECT count(*) FROM collections WHERE computed_geom IS NOT NULL")" -gt 0 ] \
	&& ok "collection geometries computed (items ordered by rank)" \
	|| fail "no computed_geom — geovisio:rank_in_collection or geometry is wrong"

step "5/8  edit propagation (incremental)"
read -r SEQ PHOTO <<<"$(hv_psql "SELECT sp.sequence_id, sp.photo_id FROM panoramax.sequence_photos sp JOIN (SELECT sequence_id, count(*) c FROM panoramax.sequence_photos GROUP BY 1 HAVING count(*) > 1 ORDER BY c LIMIT 1) s ON s.sequence_id = sp.sequence_id ORDER BY sp.rank LIMIT 1" | tr '|' ' ')"
[ -n "$PHOTO" ] || fail "no multi-photo sequence to test with"
MARK="e2e-$(hv_psql "SELECT floor(extract(epoch from now()))::bigint")"
hv_psql "UPDATE photos SET title = '$MARK' WHERE id = '$PHOTO'" >/dev/null
harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
assert_eq "$(cat_psql "SELECT content->'properties'->>'title' FROM items WHERE id = '$PHOTO'")" "$MARK" "edited title in catalog"
assert_eq "$(harvest_errors_since '2 minutes')" "0" "harvest errors after edit"

step "6/8  deletion propagation + tombstones"
hv_psql "UPDATE photos SET deleted = true WHERE id = '$PHOTO'" >/dev/null
curl -sf "$PANORAMAX_URL/api/collections/$SEQ/items?limit=1000" \
	| grep -q "\"$PHOTO\"" && fail "serve-time filter did not hide the deleted photo" \
	|| ok "deleted photo gone from /items immediately (before the sequencer ran)"
sequencer
harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
assert_eq "$(cat_psql "SELECT count(*) FROM items WHERE id = '$PHOTO'")" "0" "deleted item removed from catalog"
assert_eq "$(cat_psql "SELECT count(*) FROM deleted_items WHERE id = '$PHOTO'")" "1" "item recorded in deleted_items"

# empty a whole sequence -> tombstone, still listable via the CQL status filter
LONE_SEQ=$(hv_psql "SELECT sequence_id FROM panoramax.sequence_photos GROUP BY 1 HAVING count(*) = 1 LIMIT 1")
if [ -n "$LONE_SEQ" ]; then
	LONE_PHOTO=$(hv_psql "SELECT photo_id FROM panoramax.sequence_photos WHERE sequence_id = '$LONE_SEQ'")
	hv_psql "UPDATE photos SET deleted = true WHERE id = '$LONE_PHOTO'" >/dev/null
	sequencer
	assert_eq "$(hv_psql "SELECT status FROM panoramax.sequences WHERE id = '$LONE_SEQ'")" "deleted" "emptied sequence status"
	curl -sf "$PANORAMAX_URL/api/collections?limit=1000" | grep -q "$LONE_SEQ" \
		&& fail "tombstone leaked into the default (unfiltered) collections listing" \
		|| ok "tombstone hidden from default listing"
	# limit=1000: the listing is paginated (ordered by id, 100 per page), so
	# without it this check only sees page one and passes or fails depending
	# on where the tombstone's UUID happens to sort
	curl -sf -G "$PANORAMAX_URL/api/collections" \
		--data-urlencode "filter=status IN ('deleted','ready') AND updated > '2000-01-01T00:00:00.000000+00:00'" \
		--data-urlencode "limit=1000" \
		| grep -q "$LONE_SEQ" && ok "tombstone served via the harvester's CQL filter" \
		|| fail "tombstone NOT served via the status filter — deletions would never propagate"
	harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
	assert_eq "$(cat_psql "SELECT count(*) FROM collections WHERE id = '$LONE_SEQ'")" "0" "tombstoned collection dropped by the catalog"
	hv_psql "UPDATE photos SET deleted = false WHERE id = '$LONE_PHOTO'" >/dev/null
fi

step "7/8  restore"
hv_psql "UPDATE photos SET deleted = false, title = NULL WHERE id = '$PHOTO'" >/dev/null
sequencer
harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
assert_eq "$(cat_psql "SELECT count(*) FROM items WHERE id = '$PHOTO'")" "1" "restored item back in catalog"
assert_eq "$(cat_psql "SELECT count(*) FROM items")" "$(hv_psql "SELECT count(*) FROM panoramax.sequence_photos")" "catalog items == memberships after churn"

step "8/8  pystac validation"
"$WORK_DIR/venv/bin/python" - "$PANORAMAX_URL" <<'EOF'
import json, sys, urllib.request
import pystac
base = sys.argv[1]
col = json.load(urllib.request.urlopen(f'{base}/api/collections?limit=1'))['collections'][0]
pystac.Collection.from_dict(col).validate()
item = json.load(urllib.request.urlopen(f"{base}/api/collections/{col['id']}/items?limit=1"))['features'][0]
pystac.Item.from_dict(item).validate()
print('  \033[32m✓ collection + item validate against the STAC schemas\033[0m')
EOF

if [ "$KEEP_UP" = "0" ]; then
	docker compose -f "$META_CATALOG/docker-compose.yml" down >/dev/null 2>&1
	echo; echo "${GREEN}${BOLD}e2e federation test PASSED${RESET} (catalog stack stopped; --keep-up to leave it running)"
else
	echo; echo "${GREEN}${BOLD}e2e federation test PASSED${RESET} (catalog left running: db :5439, harvester in $WORK_DIR/venv)"
fi
