# Migrate `Photo.detected_objects` to one format (prod)

**Status, 2026-10-27:** archaeology, inventory, backed-up batch migration and
local production-dump rehearsal complete. The local dump now has explicit flags
on every stored object, with unchanged reader verdicts. Worker precomputed
payloads and API worker-result requests normalize missing flags before storage.
Production deployment/execution and consumer fallback removal remain.
Originally parked on 2026-09-20 at the operator's request to migrate after
some eyeballing.

## What is established

The read-side compatibility rule lives in `backend/common/detections.py`,
extracted from the worker by `df422d72` (2026-09-20). A persisted `blurred`
flag wins; otherwise confidence is compared with `BLUR_CONFIDENCE = 0.4`,
and absent/null confidence means true. `should_blur()` itself computes the
write-side decision; `is_blurred()` prefers the persisted flag.

The migration should persist the existing reader's decision, with provenance
for derived flags. This does **not** establish that the stored rectangle
matches the pixels. Keep representation migration and pixel/geometry repairs
separate: never invent confidence, change boxes, or rerun a detector as part
of this migration.

### Git evidence (writer dates, not deployment dates)

| Commit | Date | Evidence |
|---|---|---|
| `8cf95564` | 2025-09-16 | `anonymize.py` writes `{objects, model_name}` with `{class_id, class_name, blur, bbox}` objects; applies Gaussian blur to stored detections. Neither confidence nor a flag is stored. |
| `5cc1806f` | 2026-02-14 | Adds manual overrides: `{objects, manual: true}`, empty on skip; manual rectangles have `class_id: null`, `blur: 500`, and **no flag**. Moves Gaussian blur into `blur.py`. |
| `5c7a1447` | 2026-02-22 | Replaces Gaussian blur with a uniform color fill inside each clipped rectangle. |
| `6ca739e1` | 2026-02-22 | Adds a contrasting doodle over the uniform fill. Thus doodles predate confidence storage. |
| `48fb8ec7` | 2026-06-12 | Stores rounded confidence and scale, passes `MIN_CONFIDENCE = 0.4` to the detector, and still paints every recorded detection. |
| `bc449484` | 2026-06-13 | Splits detection floor (`0.25`) from painting threshold (`0.4`), recording but leaving sub-threshold objects visible; also filters the LLM blackout. |
| `158446cc` | 2026-06-24 | Persists explicit `blurred` for model detections **and** manual rectangles. |
| `df422d72` | 2026-09-20 | Shares the compatibility reader with the API; restricts non-owner/non-moderator detections responses to `blurred_only()`. |
| `8655f57e`, `0df48065` | 2026-10-13 | Remove workbench scripts and enrich from this repository in the repo split. |
| `89e26aa4` | 2025-08-30 | Initial schema declares `detected_objects` as `sa.JSON()`, still matched by the model. The inventoried database also reports **`json`, not `jsonb`**. |

The history supports four useful reader cases, not four disjoint chronological
eras: manual objects also existed without flags. The June 12 confidence-only
writer paints every recorded detection, but its floor is already 0.4; the
current fallback therefore agrees for those stored confidences. No change
to `BLUR_CONFIDENCE` after its introduction was found in this history. The
old module comment's suggestion that it may have moved several times was
unsupported.

Reproduce the key checks with, for example:

```sh
git show 48fb8ec7 -- backend/worker/anonymize.py backend/worker/detections.py
git show bc449484 -- backend/worker/anonymize.py backend/worker/detections.py
git show 158446cc -- backend/worker/anonymize.py backend/worker/photo_processor.py
git log -p -S BLUR_CONFIDENCE -- backend/worker/detections.py backend/common/detections.py
```

### Corrections to the original plan

- Capture month is not writer/deployment chronology: old photos can be uploaded
  or processed later. The original September workbench counts had no saved query
  or artifact here; they are superseded by the reproducible inventory below.
- The claim that enrich had switched to the uncredentialed public detections
  endpoint was not supported by the cited commit. `df422d72` only updates comments
  on its two local threshold copies; both still derive decisions from mirrored
  data immediately before removal in the repo split. The separate workbench
  repository's current behavior needs its own check.
- `blurred_only(old) == blurred_only(new)` cannot hold literally for migrated
  dictionaries: adding flags/provenance changes the returned objects. Compare
  selected objects after removing **only the keys added by the migration**, and
  independently compare object order, geometry, and each object's blur verdict.
- A confidence absent from storage cannot be recovered from the record. Running
  a detector on anonymized derivatives is a new inference, not recovery of the
  original confidence; it may return some detections, including false positives.
- The worker accepts precomputed detections and persists them verbatim
  (`AnonymizationOverride`, `PhotoProcessor.create_optimized_sizes`). A one-time
  backfill alone does not stop old payloads from reintroducing the legacy shape.
  **Addressed by this change:** normalize missing flags/provenance in the worker
  override model, again when processing a precomputed payload, and in the API's
  `ProcessedPhotoData` validator (which also covers older deployed workers).

## Inventory of the local production dump

On 2026-10-27 the operator confirmed that the local database currently contains
a production dump. This is a production-data rehearsal baseline, **not a fresh
query of the live production server**; the dump time is not recorded here.
The script uses a repeatable-read, read-only transaction and includes deleted
and unfinished photos. Full counts, per-month/model/manual/status/deletion
groups, processing-date ranges and bounded issue IDs are saved in
[the inventory report](../reports/detections-inventory-2026-10-27.json).

| Object format | Photos containing it | Objects | Read as blurred | Read as visible |
|---|---:|---:|---:|---:|
| No confidence, no flag | 9,578 | 83,735 | 83,735 | 0 |
| Confidence, no flag | 939 | 8,128 | 7,629 | 499 |
| Explicit boolean flag | 20,287 | 93,686 | 71,347 | 22,339 |
| **Total nonempty** | **30,804** | **185,549** | **162,711** | **22,838** |

No photo in this dump mixes those formats. **10,517 photos / 91,863 objects**
need flags. Other rows: 70,423 with an empty objects array, 863 with exactly
`{}`, and 164 SQL NULLs (155 authorized, nine errored). There are 269 manual
containers, all empty skips; no nonempty manual records in this dump.
There are 512 deleted photos, including 86 with legacy objects.

`processed_at` ranges are consistent with the writer commits:

| Format | First processed (UTC) | Last processed (UTC) |
|---|---|---|
| No confidence, no flag | 2025-09-24 16:00:29.689729 | 2026-06-11 05:55:36.564365 |
| Confidence, no flag | 2026-06-12 21:17:01.054392 | 2026-06-23 05:57:56.647739 |
| Explicit flag | 2026-06-25 08:14:49.447869 | 2026-10-25 16:10:56.362868 |

No malformed objects, non-boolean flags, invalid confidences, non-integer,
negative, empty or reversed boxes were found. **135 boxes on 39 photos exceed
the stored image dimensions**, all without confidence/flag. Some samples fit
swapped dimensions, suggesting an orientation issue; this is not yet a verified
explanation. Keep coordinates untouched and review these photos separately.
An empty container or array does not prove that the detector ran successfully.

Run the inventory again with an explicitly supplied database URL environment
variable (no implicit dotenv or default database target):

```sh
backend/.venv/bin/python scripts/inventory_detections.py \
  --database-url-env DATABASE_URL --source 'describe database/dump and date' \
  > /tmp/detections-inventory.json
```

`--input rows.jsonl` also supports an offline stream of rows matching the
script's `PHOTO_SQL` projection; decoded `detected_objects` JSON is expected.
The report contains counts and bounded IDs, not boxes or database credentials.
Focused tests do not connect to or clear the database:

```sh
backend/.venv/bin/python -m pytest scripts/tests/test_inventory_detections.py -q
```

## Implemented migration and rehearsal

`scripts/migrate_detections.py` offers `migrate`, `verify`, and `restore`.
Migrate/restore default to dry run. The migration scans by ID, holds row locks
through backup and update, and commits each batch separately. It uses a
compare-and-swap UPDATE and checks returned JSON text against the exact target.
Every proposed change also passes independent checks of existing fields,
object order, per-object verdicts and the public filtered projection.

Apply requires a new backup directory. A checksummed manifest records the
database identity, threshold and original ID range; each private batch file
contains the exact old/new JSON texts. Files and their directory entries are
fsynced before UPDATE. An exclusive backup-directory lock prevents overlapping
runs against the same backup. `--resume` reuses that manifest and rescans the
original range; completed rows are no-ops. Backups of interrupted transactions
remain valid, and duplicate retry backups are deduplicated. Checksum failures,
ambiguous backup histories and changed original payloads stop the operation.

Verification compares all backed-up rows with the saved target. Restore only
replaces a column still equal to its saved migrated text, skips original values
(including uncommitted batches), and refuses later edits or missing photos.
Restore commits per batch, so a conflict can leave earlier batches restored;
rerunning safely skips those. Other photo columns are never assigned.

With `DATABASE_URL` already set for the intended target:

```sh
# Inspect first; this uses one read-only repeatable-read snapshot.
backend/.venv/bin/python scripts/migrate_detections.py migrate \
  --database-url-env DATABASE_URL --source 'describe database and date' --dry-run

# Use a new backup directory; keep it until verification/rollback needs end.
backend/.venv/bin/python scripts/migrate_detections.py migrate \
  --database-url-env DATABASE_URL --source 'describe database and date' \
  --apply --backup-dir oneoff/detections-backup

backend/.venv/bin/python scripts/migrate_detections.py verify \
  --database-url-env DATABASE_URL --backup-dir oneoff/detections-backup

# After interruption, use the same source label and original --after-id if any.
backend/.venv/bin/python scripts/migrate_detections.py migrate \
  --database-url-env DATABASE_URL --source 'describe database and date' \
  --apply --resume --backup-dir oneoff/detections-backup

# Inspect rollback; add --apply only to perform the restoration.
backend/.venv/bin/python scripts/migrate_detections.py restore \
  --database-url-env DATABASE_URL --backup-dir oneoff/detections-backup --dry-run
```

The 2026-10-27 local rehearsal changed **10,517 photos / 91,863 objects**, adding
91,364 true flags and 499 false flags. All **185,549 objects** are now explicit.
All backed-up rows match the saved targets; a second full dry run proposes zero
changes; restore dry-run can restore all 10,517 with zero conflicts. The full
reader totals remain 162,711 blurred / 22,838 visible. Empty values, group photo
counts and the 135 dimension exceptions on 39 photos are unchanged. No pixel or
geometry repair was performed; history supports the representation decisions.

Evidence is saved beside the original inventory:

- [Applied changes](../reports/detections-migration-apply-2026-10-27.json)
- [Verification](../reports/detections-migration-verify-2026-10-27.json)
- [Idempotence](../reports/detections-migration-idempotence-2026-10-27.json)
- [Restore dry run](../reports/detections-migration-restore-dry-run-2026-10-27.json)
- [After inventory](../reports/detections-inventory-after-2026-10-27.json)

The 31 MB of raw backups remain local in the gitignored private directory
`oneoff/detections-migration-2026-10-27/`; they are not committed. Rehearsal
drivers and offline reconciliation probes live in `oneoff/scripts/`.

Validation: **75 focused tests passed**, including seven disposable-PostgreSQL
tests covering exact restoration, interrupted transactions/resume, backup
failure, later edits, compare-and-swap rollback and concurrent writer blocking.
The API scope/write-boundary tests use mocked DB sessions. Four additional
checks of the real worker override model passed inside its container using
stdlib unittest (the image does not include pytest). No database-clearing
integration tests were run. Actual restore was tested in disposable databases;
the full local production dump remains migrated.

## Production rollout and remaining cleanup

The batch implementation, backup/restore path, writer normalization and local
rehearsal above complete the preparation. Remaining production steps follow;
do not equate this local dump with a fresh live-production query.

1. **Resolve pixel questions from history first.** The source establishes that
   writers attempted to paint all no-confidence boxes. If pixel checks are
   needed, review a sample spanning Gaussian blur, color fill, doodles and the
   39 dimension exceptions. For doodles, the operator identifies the large
   uniform-color regions inside rectangles as the useful signal: test for
   uniform/near-uniform plateaus around the drawn strokes, accounting for image
   compression and naturally flat/white/black images. A generic Laplacian ratio
   is not established as useful across all three rendering styles. Neither
   triage score nor a visual repair should silently change migration verdicts.
2. **Apply the implemented idempotent, resumable batch migration.** Default to `--dry-run`,
   count proposed changes exactly, and transact each batch. Cursor by `id`
   (the model has no general-purpose `updated_at` column); define concurrent
   writer handling explicitly, using a row lock or comparison with the backed-up
   column before update. Invalid shapes need explicit reporting, not coercion.
   Existing boolean flags are untouched. For absent flags, persist `is_blurred()`:
   confidence-only gets the 0.4 decision, no-confidence gets true, and legacy
   manual rectangles also get true. Record that **both** kinds of backfill are
   derived (e.g. `blurred_from: legacy-no-confidence` / `legacy-confidence-0.4`),
   without overwriting existing provenance. Preserve every other key and array
   position, including `bbox`, `class_id`, `model_name`, `manual` and sub-threshold
   detections. Leave NULL/`{}`/empty arrays untouched.
3. **Back up before each write.** Save `id, detected_objects` for every affected
   row durably before its transaction commits, with a manifest and a restore
   procedure that refuses to overwrite a subsequent edit. This column is not
   reconstructible. A report of counts is not a backup.
4. **Verify every changed row during rehearsal and application.** Compare
   `is_blurred()` per object, compare the `blurred_only()` projection after
   stripping only fields added by this migration, and assert that all preexisting
   keys/values and the container are preserved. The 499 confidence-only visible
   objects must stay outside the public response. Re-running must propose zero
   changes. Re-inventory afterwards and retain the before/after evidence.
5. **Deploy the normalized write boundaries before reader cleanup.** The API
   covers older workers as well as new worker precomputed payloads. Account for
   direct-SQL importers and confirm the deployed API version. The local rehearsal
   is complete; a fresh live-prod inventory and backup are still needed for
   production execution.
6. **Remove consumer fallbacks only after rollout is complete.** Update
   `is_blurred()` and the worker's precomputed/pyramid/blackout consumers. Retain
   confidence threshold logic for **new model decisions** in the writer. Check
   the separate workbench repository for its two old copies; removal from this
   checkout did not prove their removal from the deployed service.

The public endpoint's scope remains important throughout: recorded-but-visible
boxes stay available to owners/moderators and stay out of anonymous responses.
Anonymization skips must remain deliberate skips. Re-detection of originals,
if ever wanted, is a separate task.

## Done when

All stored objects in production have explicit boolean flags, incoming writes
preserve that invariant, before/after behavior checks pass, the inventory shows
zero legacy objects, and consumers no longer derive old decisions. Geometry
issues found during review are documented separately; the migration must not
silently claim to repair them.
