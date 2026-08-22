#!/usr/bin/env fish
# Export the tables the enrichment workbench feeds on, straight out of PROD into
# the share the dev4 VM reads as /shared/. Replaces exporting them by hand from
# the WebStorm DB browser.
#
# Sibling of the full prod->host-dev restore, and deliberately much smaller:
# that one is destructive (compose down, volume rm, pg_restore of everything)
# and holds the backend lock throughout. This one is READ-ONLY on prod, writes
# nothing anywhere but its output files, needs no lock, and disrupts neither
# end. Safe to run at any time, including while the host dev stack is up.
#
#   REMOTE=<prod ssh host> ./export_prod_csv.fish [OUT_DIR]
#
# OUT_DIR defaults to /d/shared/dev4 — the host's view of what the VM sees as
# /shared/. REMOTE=local exports the local docker stack instead, which rehearses
# everything except the ssh hop.
#
# ── one snapshot, one stream per table ───────────────────────────────────────
# Each COPY is its own transaction, so prod could change between them: an
# annotation written in the gap can reference a photo another file has not got,
# and the loader drops such rows silently (WHERE photo_id IN (SELECT id FROM
# photos)). So one session opens a REPEATABLE READ transaction, publishes its
# snapshot with pg_export_snapshot(), and holds it; every COPY session then
# joins THAT snapshot with SET TRANSACTION SNAPSHOT. All tables come from one
# instant, each on its own clean stream into its own file.
#
# This is the mechanism parallel pg_dump uses, and unlike splitting one stream
# it does not care how many tables there are — adding a table is one line in
# EXPORTS below, not another channel to demultiplex.
#
# The holder keeps itself alive with a server-side pg_sleep rather than a local
# sleep process: the only thing running on this side is the ssh, so releasing
# the snapshot is one kill with nothing orphaned. That sleep is also the leak
# bound — if this script dies, prod frees the snapshot after at most that long.
#
# ── why CSV rather than pg_dump ──────────────────────────────────────────────
# pg_dump would hand us an atomic multi-table snapshot for free, but buys it
# with two things worth more:
#   * it CANNOT filter rows — its only selectors are schema/table patterns,
#     there is no --where. Restricting an export to certain users would be
#     impossible; here it is one predicate (PHOTO_WHERE, below).
#   * it is rigid against schema drift. Prod lags dev on migrations, and while
#     pg_dump survives dev ADDING a column, a rename or a type change fails it
#     outright ('column "tag" of relation ... does not exist', 'invalid input
#     syntax for type json'). CSV lands in staging tables the loader owns, where
#     drift is absorbed by one explicit line in an INSERT.
#
# The users table is deliberately NOT exported: prod account rows are PII and the
# VM has no business holding them. The loader mints stub users for the owner_ids
# it finds, which is all FK integrity needs.
#
# Then, on the VM:
#   enrich/db/seed_dev_from_dump.sh /shared/photos.csv /shared/photo_annotations.csv

set -l out_dir $argv[1]
test -n "$out_dir"; or set out_dir /d/shared/dev4

# Row filter, applied to photos and followed through to their annotations so the
# set stays referentially closed. Default takes everything. To export one owner:
#   set -x PHOTO_WHERE "owner_id = <uuid>"
set -q PHOTO_WHERE; or set -l PHOTO_WHERE true

# How long the snapshot may stay pinned on prod if this script dies. It holds
# back vacuum for that long in the worst case, so keep it just above the time a
# full export actually takes.
set -q SNAPSHOT_HOLD; or set -l SNAPSHOT_HOLD 1200

# What to export: one "table|SELECT" per line. Add a table by adding a line.
# Order is not load-bearing (one snapshot covers them all) but referencing
# tables are listed first so that even a snapshot-less fallback stays sane.
set -l EXPORTS \
    "photo_annotations|SELECT * FROM photo_annotations WHERE photo_id IN (SELECT id FROM photos WHERE $PHOTO_WHERE)" \
    "photos|SELECT * FROM photos WHERE $PHOTO_WHERE"

if not set -q REMOTE
    echo "REMOTE is unset — set it to the prod ssh host (the same one the restore" >&2
    echo "script uses), or REMOTE=local to rehearse against the local stack:" >&2
    echo "    REMOTE=hillview-prod" (status filename) "$out_dir" >&2
    exit 2
end

if not test -d $out_dir
    echo "OUT_DIR does not exist: $out_dir" >&2
    exit 2
end

# The way into a psql on the target stack. SQL always arrives on stdin — never
# as a command-line argument — so nothing has to survive a second round of shell
# quoting, and snapshot ids and WHERE clauses can contain whatever they like.
# Auth is the container's local socket, so no database password is needed
# anywhere; ssh is the only credential.
#
# A LIST, deliberately not a function: fish cannot start functions in the
# background ("At the moment, functions cannot be started in the background" —
# docs/language.html, Job control). The snapshot holder below IS a background
# job, and wrapping it in a function does not fail loudly — it mis-runs, with
# pg_sleep returning instantly and the transaction closing under you, so the
# export dies later with "invalid snapshot identifier".
set -g PSQL_CMD
if test "$REMOTE" = local
    set PSQL_CMD docker exec -i hillview_postgres psql -U hillview -d hillview -qAt -v ON_ERROR_STOP=1
else
    set PSQL_CMD ssh $REMOTE "docker exec -i hillview_postgres psql -U hillview -d hillview -qAt -v ON_ERROR_STOP=1"
end

echo "source: $REMOTE   out: $out_dir   filter: $PHOTO_WHERE"

# ── open the snapshot ────────────────────────────────────────────────────────
set -g snapfile (mktemp)
begin
    # milliseconds, so no quoting; covers the gap between statements
    echo "SET idle_in_transaction_session_timeout = 60000;"
    echo "BEGIN ISOLATION LEVEL REPEATABLE READ;"
    # both facts on one line: the snapshot to join, and the backend to shoot
    # afterwards. Emitting them together means one thing to wait for, not two.
    echo "SELECT pg_export_snapshot() || ' ' || pg_backend_pid();"
    # server-side keep-alive: psql stays busy here, holding the transaction, while
    # our stdin has already closed. Nothing local to orphan.
    echo "SELECT pg_sleep($SNAPSHOT_HOLD);"
end | $PSQL_CMD >$snapfile 2>&1 &
set -g holder_pid $last_pid

set -g snapshot ""
set -g holder_backend ""
for i in (seq 1 60)
    # psql flushes after each statement, so this lands well before the pg_sleep
    # finishes. Match the shape rather than trusting line 1.
    set -l line (string match -r '^[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+ [0-9]+$' <$snapfile | head -1)
    if test -n "$line"
        set snapshot (string split ' ' -- $line)[1]
        set holder_backend (string split ' ' -- $line)[2]
        break
    end
    sleep 0.5
end

function _release
    # Terminate SERVER-side. Killing the local ssh does not reap the remote psql,
    # and the holder is ACTIVE inside pg_sleep, so idle_in_transaction_session_timeout
    # never fires against it — this is the only thing that reliably unpins the
    # snapshot. Verified: without it, a snapshot file and an open transaction
    # survive the script by the full pg_sleep duration.
    if test -n "$holder_backend"
        echo "SELECT pg_terminate_backend($holder_backend);" | $PSQL_CMD >/dev/null 2>&1
    end
    test -n "$holder_pid"; and kill $holder_pid 2>/dev/null
    rm -f $snapfile
end

if test -z "$snapshot"
    echo "!! could not open a snapshot on $REMOTE:" >&2
    cat $snapfile >&2
    _release
    exit 1
end
echo "snapshot: $snapshot"

# ── copy each table out of that one snapshot ─────────────────────────────────
set -l failed 0
for spec in $EXPORTS
    set -l table (string split -m1 '|' -- $spec)[1]
    set -l select (string split -m1 '|' -- $spec)[2]
    set -l final $out_dir/$table.csv
    set -l part $out_dir/.$table.csv.part

    echo "== $table =="
    # COPY … TO STDOUT (not \copy): the server streams it and psql prints no
    # command tag on stdout, so the byte stream is pure CSV. SELECT * on purpose —
    # a pinned column list would silently drop whatever prod grows next, and the
    # loader is header-driven precisely so new columns arrive on their own.
    begin
        echo "BEGIN ISOLATION LEVEL REPEATABLE READ;"
        echo "SET TRANSACTION SNAPSHOT '$snapshot';"
        echo "COPY ($select) TO STDOUT WITH (FORMAT csv, HEADER);"
        echo "COMMIT;"
    end | $PSQL_CMD >$part
    or begin
        # ssh reports the remote exit status, and a connection dropped mid-stream
        # exits non-zero too, so this doubles as the truncation guard: a partial
        # transfer never reaches the rename, and the previous good CSV stands.
        echo "!! $table export failed — leaving the previous $final untouched" >&2
        rm -f $part
        set failed 1
        break
    end

    # cheap check before publishing: catches the remote writing a diagnostic to
    # stdout instead of data
    if not head -1 $part | string match -qr '^id,'
        echo "!! $table output is not CSV (no id, header) — not publishing" >&2
        rm -f $part
        set failed 1
        break
    end

    # publish atomically: same filesystem, so the rename is all-or-nothing and the
    # VM sees either the whole new file or the whole old one — never a torn one,
    # which matters because the loader truncates before it reloads
    mv -f $part $final
    or begin
        set failed 1
        break
    end
    echo "   "(du -h $final | cut -f1)"  ->  $final"
end

_release
test $failed -eq 1; and exit 1

echo
ls -lh $out_dir/photos.csv $out_dir/photo_annotations.csv
echo
echo "next, on the VM:"
echo "  enrich/db/seed_dev_from_dump.sh /shared/photos.csv /shared/photo_annotations.csv"
