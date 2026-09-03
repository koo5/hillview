#!/bin/bash
# End-to-end federation test: drive the REAL Panoramax meta-catalog harvester
# against this repo's panoramax container and assert that every contract the
# federation depends on actually holds.
#
#   ./backend/panoramax/scripts/e2e_federation.sh              # full run
#   ./backend/panoramax/scripts/e2e_federation.sh --heavy      # + production-shaped 50k-photo corpus
#   ./backend/panoramax/scripts/e2e_federation.sh --no-seed    # use existing photos
#   ./backend/panoramax/scripts/e2e_federation.sh --keep-up    # don't stop the catalog after
#   ./backend/panoramax/scripts/e2e_federation.sh --keep-load  # --heavy: leave the corpus in the DB
#   ./backend/panoramax/scripts/e2e_federation.sh --cleanup-load  # remove a kept corpus and exit
#   ./backend/panoramax/scripts/e2e_federation.sh --down       # tear the catalog down and exit
#
# --heavy (LOAD_PHOTOS=50000 LOAD_USERS=40 LOAD_YEARS=3 LOAD_SEED=1 to tune)
# additionally bulk-generates a production-shaped corpus straight into the DB
# (generate_load.py: many users, singles + walks over years, ~10% ineligible
# rows of every kind) and, on top of the phases below, checks:
#   2b. sequencer output == the generator's independently computed expectation
#       (sequences, memberships, singles), and a second pass changes nothing
#   4b. paging: every /api/collections page and every /items page of the
#       largest sequence, no duplicates, ranks strictly increasing
#   5b. churn across users: 200 random edits -> `updated` filter returns
#       exactly the touched sequences -> incremental harvest lands all 200
#   6b. deactivating the heaviest user tombstones all their sequences, the
#       catalog drops them; reactivating revives the SAME sequence ids
#   plus timings (sequencer pass, full/incremental harvest, page latency).
#   Takes a while; the corpus is removed at the end unless --keep-load.
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

LOAD_PHOTOS="${LOAD_PHOTOS:-50000}"
LOAD_USERS="${LOAD_USERS:-40}"
LOAD_YEARS="${LOAD_YEARS:-3}"
LOAD_SEED="${LOAD_SEED:-1}"
GENERATOR="$REPO_ROOT/backend/panoramax/scripts/generate_load.py"

SEED=1
KEEP_UP=0
HEAVY=0
KEEP_LOAD=0
for arg in "$@"; do
	case "$arg" in
		--no-seed) SEED=0 ;;
		--keep-up) KEEP_UP=1 ;;
		--heavy) HEAVY=1 ;;
		--keep-load) KEEP_LOAD=1 ;;
		--cleanup-load) python3 "$GENERATOR" --cleanup; exit 0 ;;
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

now_s()  { date +%s.%N; }
since()  { awk -v a="$(now_s)" -v b="$1" 'BEGIN { printf "%.1fs", a - b }'; }
jsonq()  { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {}, {'d': d}))" "$1" "$2"; }
METRICS=()
metric() { METRICS+=("$1"); echo "    ⏱ $1"; }

cd "$REPO_ROOT"
[ -f .env ] || fail ".env missing — copy one in before running (see .env.example)"
set -a; . ./.env; set +a
[ -n "${PANORAMAX_DB_PASSWORD:-}" ] || fail "PANORAMAX_DB_PASSWORD unset in .env"
[ -d "$META_CATALOG" ] || fail "meta-catalog not found at $META_CATALOG (set META_CATALOG=)"

step "1/8  hillview stack"
./compose.sh --profile panoramax up --build -d postgres api worker panoramax >/dev/null
until curl -sf "$PANORAMAX_URL/api/health" >/dev/null 2>&1; do sleep 2; done
ok "panoramax API healthy at $PANORAMAX_URL"
[ "$(hv_psql "SELECT count(*) FROM alembic_version WHERE version_num = '033_add_panoramax_schema'")" = "1" ] \
	|| fail "migration 033 not applied (api prestart should have done it)"
ok "migration 033 applied"
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

if [ "$HEAVY" = "1" ]; then
	step "2b/8 heavy: generate $LOAD_PHOTOS photos / $LOAD_USERS users / $LOAD_YEARS years (seed $LOAD_SEED)"
	mkdir -p "$WORK_DIR"
	LOAD_SUMMARY="$WORK_DIR/load_summary.json"
	T=$(now_s)
	python3 "$GENERATOR" --photos "$LOAD_PHOTOS" --users "$LOAD_USERS" --years "$LOAD_YEARS" \
		--seed "$LOAD_SEED" --gap-hours "${PANORAMAX_SESSION_GAP_HOURS:-3}" --summary "$LOAD_SUMMARY"
	metric "generate + COPY: $(since "$T")"
	LOAD_USER_IDS="'$(jsonq "$LOAD_SUMMARY" "\"','\".join(d['user_ids'])")'"
	LOAD_IN="owner_id IN ($LOAD_USER_IDS)"

	T=$(now_s); sequencer; metric "sequencer pass over the corpus: $(since "$T")"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE status = 'ready' AND $LOAD_IN")" \
		"$(jsonq "$LOAD_SUMMARY" "d['expected_sequences']")" "sequences for the corpus (independent expectation)"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id = sp.sequence_id WHERE s.$LOAD_IN")" \
		"$(jsonq "$LOAD_SUMMARY" "d['eligible']")" "memberships == eligible photos (ineligible rows of every kind excluded)"
	assert_eq "$(hv_psql "SELECT count(*) FROM (SELECT sp.sequence_id FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id = sp.sequence_id WHERE s.$LOAD_IN GROUP BY 1 HAVING count(*) = 1) x")" \
		"$(jsonq "$LOAD_SUMMARY" "d['expected_singles']")" "single-photo sequences"
	for u in $(jsonq "$LOAD_SUMMARY" "' '.join(k for k,v in d['per_user'].items() if not v['is_active'] or v['is_test'])"); do
		assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE owner_id = '$u'")" "0" "no sequences for inactive/test user ${u:0:8}"
	done
	# idempotence: a second pass must not touch anything (updated_at is the
	# harvester's crawl signal, so a spurious bump = a spurious re-harvest)
	BEFORE=$(hv_psql "SELECT now()")
	T=$(now_s); sequencer >/dev/null; metric "sequencer no-op pass: $(since "$T")"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE updated_at > '$BEFORE'")" "0" "second pass bumped no sequence"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE status = 'ready' AND $LOAD_IN")" \
		"$(jsonq "$LOAD_SUMMARY" "d['expected_sequences']")" "second pass created no sequence"
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
T=$(now_s)
harvester harvest "$INSTANCE_NAME" --full-harvest 2>&1 | grep -E "🎉|Collections imported: [0-9]+ col \[0" | tail -1
metric "full harvest ($TOTAL_SEQ collections / $TOTAL_PHOTOS items): $(since "$T")"
assert_eq "$(harvest_errors_since '30 minutes')" "0" "harvest errors"
assert_eq "$(cat_psql "SELECT count(*) FROM collections")" "$TOTAL_SEQ" "collections in catalog"
assert_eq "$(cat_psql "SELECT count(*) FROM items")" "$TOTAL_PHOTOS" "items in catalog"
[ "$(cat_psql "SELECT count(*) FROM providers")" -gt 0 ] && ok "providers derived" || fail "no providers — providers[*].id/name missing?"
[ "$(cat_psql "SELECT count(*) FROM collections WHERE computed_geom IS NOT NULL")" -gt 0 ] \
	&& ok "collection geometries computed (items ordered by rank)" \
	|| fail "no computed_geom — geovisio:rank_in_collection or geometry is wrong"

if [ "$HEAVY" = "1" ]; then
	step "4b/8 heavy: paging walk"
	BIG_SEQ=$(hv_psql "SELECT sequence_id FROM panoramax.sequence_photos GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
	BIG_N=$(hv_psql "SELECT count(*) FROM panoramax.sequence_photos WHERE sequence_id = '$BIG_SEQ'")
	"$WORK_DIR/venv/bin/python" - "$PANORAMAX_URL" "$TOTAL_SEQ" "$BIG_SEQ" "$BIG_N" <<'EOF'
import json, sys, time, urllib.request
base, total_seq, big_seq, big_n = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])

def walk(url, key):
    seen, pages, lat = [], 0, []
    while url:
        t = time.monotonic()
        d = json.load(urllib.request.urlopen(url))
        lat.append(time.monotonic() - t)
        pages += 1
        seen.extend(d[key])
        url = next((l['href'] for l in d['links'] if l['rel'] == 'next'), None)
    return seen, pages, lat

cols, pages, lat = walk(f'{base}/api/collections?limit=100', 'collections')
ids = [c['id'] for c in cols]
assert len(ids) == total_seq, f'collections walk: {len(ids)} != {total_seq}'
assert len(set(ids)) == len(ids), 'duplicate collection ids across pages'
assert all(c['geovisio:status'] == 'ready' for c in cols), 'tombstone in default listing'
print(f'  \033[32m✓ collections walk: {len(ids)} collections over {pages} pages, no duplicates\033[0m')
print(f'    ⏱ collections page (100): avg {sum(lat)/len(lat)*1000:.0f} ms, max {max(lat)*1000:.0f} ms')

items, pages, lat = walk(f'{base}/api/collections/{big_seq}/items?limit=100', 'features')
ranks = [f['properties']['geovisio:rank_in_collection'] for f in items]
assert len(items) == big_n, f'items walk: {len(items)} != {big_n}'
assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks), 'ranks not strictly increasing across pages'
dts = [f['properties']['datetime'] for f in items]
assert dts == sorted(dts), 'items not in capture order'
print(f'  \033[32m✓ items walk of the largest sequence: {len(items)} items over {pages} pages, ranks strictly increasing\033[0m')
print(f'    ⏱ items page (100): avg {sum(lat)/len(lat)*1000:.0f} ms, max {max(lat)*1000:.0f} ms')
EOF
fi

step "5/8  edit propagation (incremental)"
read -r SEQ PHOTO <<<"$(hv_psql "SELECT sp.sequence_id, sp.photo_id FROM panoramax.sequence_photos sp JOIN (SELECT sequence_id, count(*) c FROM panoramax.sequence_photos GROUP BY 1 HAVING count(*) > 1 ORDER BY c LIMIT 1) s ON s.sequence_id = sp.sequence_id ORDER BY sp.rank LIMIT 1" | tr '|' ' ')"
[ -n "$PHOTO" ] || fail "no multi-photo sequence to test with"
MARK="e2e-$(hv_psql "SELECT floor(extract(epoch from now()))::bigint")"
hv_psql "UPDATE photos SET title = '$MARK' WHERE id = '$PHOTO'" >/dev/null
T=$(now_s)
harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
metric "incremental harvest, 1 collection changed: $(since "$T")"
assert_eq "$(cat_psql "SELECT content->'properties'->>'title' FROM items WHERE id = '$PHOTO'")" "$MARK" "edited title in catalog"
assert_eq "$(harvest_errors_since '2 minutes')" "0" "harvest errors after edit"

if [ "$HEAVY" = "1" ]; then
	step "5b/8 heavy: churn across users (200 random edits)"
	CHURN_MARK="churn-$(hv_psql "SELECT floor(extract(epoch from now()))::bigint")"
	CHURN_IDS=$(hv_psql "SELECT string_agg(quote_literal(sp.photo_id), ',') FROM (SELECT sp.photo_id FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id = sp.sequence_id WHERE s.$LOAD_IN ORDER BY random() LIMIT 200) sp")
	EXPECT_SEQS=$(hv_psql "SELECT string_agg(sequence_id::text, ',' ORDER BY sequence_id) FROM (SELECT DISTINCT sequence_id FROM panoramax.sequence_photos WHERE photo_id IN ($CHURN_IDS)) x")
	N_EXPECT=$(echo "$EXPECT_SEQS" | tr ',' '\n' | wc -l)
	SINCE=$(hv_psql "SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00\"')")
	sleep 1
	hv_psql "UPDATE photos SET title = '$CHURN_MARK' WHERE id IN ($CHURN_IDS)" >/dev/null
	GOT_SEQS=$(curl -sf -G "$PANORAMAX_URL/api/collections" \
		--data-urlencode "filter=status IN ('deleted','ready') AND updated > '$SINCE'" --data-urlencode "limit=1000" \
		| python3 -c "import json,sys; print(','.join(sorted(c['id'] for c in json.load(sys.stdin)['collections'])))")
	[ "$GOT_SEQS" = "$EXPECT_SEQS" ] && ok "updated-filter returns exactly the $N_EXPECT touched sequences" \
		|| fail "updated-filter mismatch: expected $N_EXPECT sequences, got $(echo "$GOT_SEQS" | tr ',' '\n' | grep -c .)"
	T=$(now_s)
	harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
	metric "incremental harvest, $N_EXPECT collections changed: $(since "$T")"
	assert_eq "$(cat_psql "SELECT count(*) FROM items WHERE content->'properties'->>'title' = '$CHURN_MARK'")" "200" "all 200 edits landed in the catalog"
	assert_eq "$(harvest_errors_since '5 minutes')" "0" "harvest errors after churn"
fi

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

if [ "$HEAVY" = "1" ]; then
	step "6b/8 heavy: deactivate the heaviest user, then bring them back"
	HEAVY_USER=$(hv_psql "SELECT id FROM users WHERE username = '$(jsonq "$LOAD_SUMMARY" "d['heaviest_user']")'")
	# snapshot the READY set only: phase 6 may have left one of this owner's
	# sequences tombstoned (restored in phase 7), which must not skew the sets
	H_SEQS=$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE owner_id = '$HEAVY_USER' AND status = 'ready'")
	H_IDS=$(hv_psql "SELECT string_agg(id::text, ',' ORDER BY id) FROM panoramax.sequences WHERE owner_id = '$HEAVY_USER' AND status = 'ready'")
	H_IN="id IN (SELECT unnest(string_to_array('$H_IDS', ','))::uuid)"
	H_ITEMS=$(hv_psql "SELECT count(*) FROM panoramax.sequence_photos WHERE sequence_$H_IN")
	H_ALL=$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE owner_id = '$HEAVY_USER'")
	H_ONE=${H_IDS%%,*}
	ok "heaviest user ${HEAVY_USER:0:8}: $H_SEQS ready sequences / $H_ITEMS items"
	SINCE=$(hv_psql "SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00\"')")
	sleep 1
	hv_psql "UPDATE users SET is_active = false WHERE id = '$HEAVY_USER'" >/dev/null
	assert_eq "$(curl -sf "$PANORAMAX_URL/api/collections/$H_ONE/items?limit=1000" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['features']))")" \
		"0" "items hidden at serve time before the sequencer ran"
	T=$(now_s); sequencer; metric "sequencer pass, one heavy user removed: $(since "$T")"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE status = 'deleted' AND $H_IN")" "$H_SEQS" "all their sequences tombstoned"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequence_photos sp JOIN panoramax.sequences s ON s.id = sp.sequence_id WHERE s.owner_id = '$HEAVY_USER'")" "0" "all their memberships gone"
	GOT=$(curl -sf -G "$PANORAMAX_URL/api/collections" \
		--data-urlencode "filter=status IN ('deleted') AND updated > '$SINCE'" --data-urlencode "limit=1000" \
		| python3 -c "import json,sys; print(','.join(sorted(c['id'] for c in json.load(sys.stdin)['collections'])))")
	[ "$GOT" = "$H_IDS" ] && ok "deleted+updated filter returns exactly their $H_SEQS tombstones" \
		|| fail "tombstone filter mismatch (got $(echo "$GOT" | tr ',' '\n' | grep -c .) ids)"
	T=$(now_s)
	harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
	metric "incremental harvest, $H_SEQS collections tombstoned: $(since "$T")"
	assert_eq "$(cat_psql "SELECT count(*) FROM collections WHERE $H_IN")" "0" "catalog dropped their collections"
	assert_eq "$(cat_psql "SELECT count(*) FROM items WHERE collection_id IN (SELECT unnest(string_to_array('$H_IDS', ','))::uuid)")" "0" "catalog dropped their items"
	assert_eq "$(harvest_errors_since '5 minutes')" "0" "harvest errors after deactivation"

	hv_psql "UPDATE users SET is_active = true WHERE id = '$HEAVY_USER'" >/dev/null
	T=$(now_s); sequencer; metric "sequencer pass, heavy user back: $(since "$T")"
	[ "$(hv_psql "SELECT string_agg(id::text, ',' ORDER BY id) FROM panoramax.sequences WHERE status = 'ready' AND $H_IN")" = "$H_IDS" ] \
		&& ok "the SAME $H_SEQS sequence ids revived (identity retained)" \
		|| fail "revived sequence ids differ from the snapshot (identity lost)"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequences WHERE owner_id = '$HEAVY_USER'")" "$H_ALL" "no new sequence uuids minted for them"
	assert_eq "$(hv_psql "SELECT count(*) FROM panoramax.sequence_photos WHERE sequence_$H_IN")" "$H_ITEMS" "all their memberships back"
	T=$(now_s)
	harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
	metric "incremental harvest, $H_SEQS collections revived: $(since "$T")"
	assert_eq "$(cat_psql "SELECT count(*) FROM items WHERE collection_id IN (SELECT unnest(string_to_array('$H_IDS', ','))::uuid)")" "$H_ITEMS" "catalog has all their items again"
	assert_eq "$(harvest_errors_since '5 minutes')" "0" "harvest errors after revival"
fi

step "7/8  restore"
hv_psql "UPDATE photos SET deleted = false, title = NULL WHERE id = '$PHOTO'" >/dev/null
sequencer
harvester harvest "$INSTANCE_NAME" --incremental-harvest >/dev/null 2>&1
assert_eq "$(cat_psql "SELECT count(*) FROM items WHERE id = '$PHOTO'")" "1" "restored item back in catalog"
if [ -n "${LONE_SEQ:-}" ]; then
	# the lone photo was restored at the end of phase 6; its emptied sequence
	# must come back under the SAME uuid (former_photo_ids), not a fresh one
	assert_eq "$(hv_psql "SELECT status FROM panoramax.sequences WHERE id = '$LONE_SEQ'")" "ready" "emptied sequence revived (same uuid)"
	assert_eq "$(hv_psql "SELECT sequence_id::text FROM panoramax.sequence_photos WHERE photo_id = '$LONE_PHOTO'")" "$LONE_SEQ" "lone photo back in its original sequence"
	assert_eq "$(cat_psql "SELECT count(*) FROM collections WHERE id = '$LONE_SEQ'")" "1" "revived collection re-harvested"
fi
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

if [ "$HEAVY" = "1" ]; then
	echo; echo "${BOLD}timings${RESET}"
	for m in "${METRICS[@]}"; do echo "  ⏱ $m"; done
	if [ "$KEEP_LOAD" = "0" ]; then
		python3 "$GENERATOR" --cleanup >/dev/null || fail "corpus cleanup failed — check the trigger cascade paths"
		ok "corpus removed (--keep-load to keep it)"
	else
		ok "corpus kept in the DB (--cleanup-load to remove it)"
	fi
fi

if [ "$KEEP_UP" = "0" ]; then
	docker compose -f "$META_CATALOG/docker-compose.yml" down >/dev/null 2>&1
	echo; echo "${GREEN}${BOLD}e2e federation test PASSED${RESET} (catalog stack stopped; --keep-up to leave it running)"
else
	echo; echo "${GREEN}${BOLD}e2e federation test PASSED${RESET} (catalog left running: db :5439, harvester in $WORK_DIR/venv)"
fi
