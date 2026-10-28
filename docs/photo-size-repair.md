# Repair photo dimensions to match uploaded artifacts

`scripts/propose_photo_size_fixes.py` produces the HTML review and JSON plan.
`scripts/fix_photo_sizes.py` consumes that plan. Both tools require explicit
inputs. The repair tool never uploads, rotates, or regenerates images, and
never writes detection coordinates, source MD5, EXIF, or processing timestamps.
Its `sql` command generates standalone SQL for your usual PostgreSQL client;
generation requires no database URL or database connection.

The operator chose to keep the uploaded panorama artifacts and align metadata
with them. The standalone archive note is
[2026-09-02-panorama-stale-exr.md](incidents/2026-09-02-panorama-stale-exr.md).
Its archived source remains 156,962 × 8,366; the proposed photo-row dimensions
are 157,180 × 10,646, matching the served DZI. The full rendition's capped
8192 × 554 dimensions are unchanged.

## Prepare and review

Generate a version 2 plan with the explicit uploaded-artifact basis:

```sh
backend/.venv/bin/python scripts/propose_photo_size_fixes.py \
  --anomalies oneoff/photo-dimensions-anomalies-2026-10-27.jsonl \
  --header-checks oneoff/size-fixes-report.headers.jsonl \
  --dzi-evidence oneoff/scripts/2026-10-27_1530_dimension_panorama_detail.out.txt \
  --source-evidence docs/reports/photo-dimensions-panorama-source-2026-10-27.jsonl \
  --audit-report docs/reports/photo-dimensions-audit-2026-10-27.json \
  --match-uploaded-artifacts --output oneoff/size-fixes-report.html
```

Open `oneoff/size-fixes-report.html`. The JSON plan includes the original source
evidence, per-field artifact URL/dimensions, expected old values and processing
time. Without `--match-uploaded-artifacts`, source/output disagreement continues
to block panorama proposals. The repair tool accepts only plans with the
explicit `uploaded-artifacts` basis.

The prepared plan has **381 verified photos / 957 dimension pairs**:
188 photo-row reversals, 192 photos with four smaller-rendition metadata swaps
each, and the panorama. One deleted photo with missing artifacts stays blocked
and is skipped. Skipping an unresolved row is reported, not silently treated as
a repair.

**Applied, 2026-10-28:** the operator ran the generated SQL in production and
refreshed the local dump. [Read-only verification](reports/photo-size-repair-verified-2026-10-28.json)
confirms all 381 selected photos / 957 pairs match the plan, with zero conflicts
against the 381 rows in `public.photo_size_fix_f28e4b89a344ddce`. The following
commands describe the completed repair and its recovery path.

## Generate SQL and apply with psql

The generated files are ready under `oneoff/size-fixes.sql`, with sibling
`size-fixes.verify.sql`, `size-fixes.restore.sql` and `size-fixes.evidence.json`.
To generate a new set (output paths must not already exist):

```sh
python3 scripts/fix_photo_sizes.py sql \
  --plan oneoff/size-fixes-report.json --output oneoff/size-fixes.sql \
  --check-artifacts
```

`--check-artifacts` rereads the served image/DZI headers at generation time;
without it, generation is entirely offline and uses the reviewed plan evidence.
The generated SQL checks database state when it runs, not HTTP headers. No
Python environment or plan file is needed on the production host: copy the SQL
files and keep their evidence sidecar with your repair records.

With your usual production connection options, run:

```sh
psql -v ON_ERROR_STOP=1 -f oneoff/size-fixes.sql
psql -v ON_ERROR_STOP=1 -f oneoff/size-fixes.verify.sql
```

Apply locks the reviewed rows, checks old dimensions, processing times, deletion
state, source MD5 where recorded and artifact URLs/dimension metadata, and stores
exact before/after metadata in a persistent `public.photo_size_fix_<plan-hash>`
table. The exact name is printed by generation and appears in each SQL header.
Backup creation, repair and write verification share one transaction: any
conflict rolls everything back. Other photo columns, including detection JSON,
are not written. The deleted photo is excluded.

The backup table is kept after commit. Apply deliberately refuses to overwrite
an existing backup table: use the verification script if a client disconnected
and you are unsure whether apply committed. The companion restore script is
also transactional, checks identity and exact repaired values, and refuses to
overwrite later metadata edits:

```sh
psql -v ON_ERROR_STOP=1 -f oneoff/size-fixes.restore.sql
```

The SQL contains ordinary PostgreSQL statements without psql metacommands; it
can also run in another PostgreSQL client. Verification and restore use the
retained backup table, so keep that table until the repair is accepted.

## Direct Python alternative: dry run and apply

Set a PostgreSQL URL in an environment variable using your normal credential
mechanism; these tools do not load `.env` or infer the target database.

```sh
backend/.venv/bin/python scripts/fix_photo_sizes.py repair \
  --database-url-env DATABASE_URL --plan oneoff/size-fixes-report.json --dry-run

backend/.venv/bin/python scripts/fix_photo_sizes.py repair \
  --database-url-env DATABASE_URL --plan oneoff/size-fixes-report.json \
  --dry-run --check-artifacts
```

Dry run checks the reviewed old values, artifact URLs and processing times
against one read-only DB snapshot. `--check-artifacts` additionally rereads
served image/DZI headers with bounded reads. Apply always rechecks headers:

```sh
backend/.venv/bin/python scripts/fix_photo_sizes.py repair \
  --database-url-env DATABASE_URL --plan oneoff/size-fixes-report.json \
  --apply --backup-dir /tmp/photo-size-repair-backup
```

The backup directory must be new; choose durable storage for a production
repair. The tool checks live artifact dimensions, locks all selected rows in
ID order, validates every row, then saves/fsyncs a checksummed `repair.json`
before the first update. All row updates commit together. An invalid/missing
row, changed URL, reprocessing, metadata conflict, failed backup or failed
update aborts the transaction. Already-matching fields are idempotent.

Backups contain exact raw JSON text before/after, source identity, the full
reviewed plan and timestamped header checks. Files use mode 0600 and newly
created backup directories use 0700. Only `width`, `height` and `sizes` are
updated. Unknown rendition metadata and all other columns are preserved.

## Verify or restore

```sh
backend/.venv/bin/python scripts/fix_photo_sizes.py verify \
  --database-url-env DATABASE_URL --backup-dir /tmp/photo-size-repair-backup

backend/.venv/bin/python scripts/fix_photo_sizes.py restore \
  --database-url-env DATABASE_URL --backup-dir /tmp/photo-size-repair-backup --dry-run

backend/.venv/bin/python scripts/fix_photo_sizes.py restore \
  --database-url-env DATABASE_URL --backup-dir /tmp/photo-size-repair-backup --apply
```

Verification fails if a backed-up row remains at its original value, has been
reprocessed, or has conflicting edits. Restoration permits only the exact
backed-up repaired/original metadata, checks photo identity/status and database
identity, and restores exact original JSON text in one transaction. Later edits
to `sizes` or photo dimensions are never overwritten by restoration. A backup
written before a failed transaction is safe: rows still at original values are
recognized as such. Detection edits remain independent and are not restored.

Tests in `scripts/tests/test_fix_photo_sizes.py` create/drop only uniquely named
disposable databases when `DETECTIONS_TEST_ADMIN_URL` is set. They never clear
or update the configured source database.
