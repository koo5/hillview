# Apply the reviewed detections-format backfill with SQL

**Applied to production, 2026-10-28:** confirmed by the operator. The retained
backup table is `public.detections_fix_270aa7396d26a976`. The instructions below
document that completed application and its verification/restoration paths.
The subsequent production redump is independently verified: all 10,517 backup
targets match, all 185,765 objects have explicit flags, zero legacy objects
remain, and a full migration dry run proposes zero changes. Reader verdicts,
geometry and the 381 earlier size repairs are preserved. See
[production verification](reports/detections-migration-production-verified-2026-10-28.json).

The 2026-10-28 report was reviewed against the production redump after the size
repairs. SQL export covers **10,517 photos / 91,863 objects**, adding 91,364 true
flags and 499 false flags, plus missing derivation provenance. Existing flags,
confidences, boxes, object order and other JSON fields are preserved. Only
`photos.detected_objects` is updated; no image bytes or size metadata change.
Deleted rows remain in scope, as in the inventory and original migration plan.

## Generated files and production use

- `oneoff/detections-format.sql`: apply.
- `oneoff/detections-format.verify.sql`: verify the retained backup's targets.
- `oneoff/detections-format.restore.sql`: restore exact original JSON text.
- `oneoff/detections-format.evidence.json`: counts, source snapshot identity,
  target IDs and plan digest. Keep this with the SQL as the generation record.

In your production `psql` session, with the files available relative to the
client's working directory:

```sql
\set ON_ERROR_STOP on
\i oneoff/detections-format.sql
\i oneoff/detections-format.verify.sql
```

Apply loads the exact reviewed before/after JSON into a temporary staging table,
locks the selected photo rows in ID order and checks their raw detection JSON,
source MD5, filename, processing time, status and deletion flag. It saves changed
rows in **`public.detections_fix_270aa7396d26a976`**, updates the column and checks
every target. All work shares one transaction: a conflict or failed check aborts
the entire migration. Rows already at the exact target are recognized and skipped.
An existing backup table causes apply to fail rather than overwrite history.

No Python runtime, database URL handling or JSON plan file is needed on the
production host. The SQL files use ordinary PostgreSQL statements without psql
metacommands, so they can also run through another PostgreSQL client.

Verification checks all backed-up targets and their photo identities. If apply
disconnects and its outcome is unclear, use verification instead of rerunning
apply into the same backup table. Keep the backup table until the migration is
accepted. To restore, in the same production client:

```sql
\i oneoff/detections-format.restore.sql
```

Restore recognizes exact original/repaired values, refuses later detection or
source-identity edits, restores the exact original JSON text, and verifies it
before committing. It leaves all other columns alone. Repeated restore is safe.

## Regenerate from a reviewed dump

The migration's `--sql-output` option is allowed only during dry run. It uses the
same normalizer and independent behavior/field verifier as the HTML report and
the backed-up Python migration. Generation reads one repeatable-read, read-only
snapshot; it does not apply the SQL. Output paths must be new:

```sh
backend/.venv/bin/python scripts/migrate_detections.py migrate \
  --database-url-env DATABASE_URL \
  --source 'reviewed production redump after size metadata repair, 2026-10-28' \
  --dry-run --sql-output oneoff/detections-format.sql
```

`--review-html` can be supplied too, generating HTML and SQL from the same
snapshot. The source connection is local for generation; the resulting SQL
checks production values when applied. Newly inserted legacy rows outside the
exported ID set are not implicitly added to this reviewed migration. Verify a
fresh inventory before deploying flag-only readers.

Generation counts are saved in
[the export report](reports/detections-migration-sql-export-2026-10-28.json).
Database tests cover literal quoting, manual and confidence-based entries,
existing flags, SQL NULL/empty values, missing rows, source/detection conflicts,
atomic rollback and exact restoration. They use uniquely named disposable
databases and never clear the configured source dump.

All 37 focused migration/SQL tests passed. The exact exported files were also
run through `psql` against a disposable copy of all **10,517 affected photos**:
apply and verification passed, every field/geometry/verdict invariant passed,
and restoration reproduced the exact original JSON and other columns. The
source dump stayed read-only. See the
[full SQL rehearsal report](reports/detections-migration-sql-rehearsal-2026-10-28.json).
The operator subsequently confirmed production application on 2026-10-28.
The fresh inventory is complete. Flag-only readers and normalized write
boundaries are now prepared in the same branch; deploy them together. Historical
read rules remain in `common.legacy_detections` for backup verification.
