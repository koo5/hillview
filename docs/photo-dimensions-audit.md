# Photo dimension audit, 2026-10-27

Read-only audit of all **102,425 rows** in the operator-restored production dump.
No database values, image pixels, or detection boxes were changed. The audit
includes deleted and unfinished photos. This is a local dump, not a fresh live
production query.

**Production follow-up, 2026-10-28:** the operator applied the generated SQL to
production and refreshed the local dump. Read-only verification finds all
**381 repaired photos / 957 dimension pairs** at their planned values; the
retained production backup table has 381 rows and zero conflicts. The fresh
all-row audit scans 102,448 photos: 98,120 exact matches, 4,163 ordinary full
downscales, 164 unfinished/invalid-dimension rows and one exact reversal, the
deliberately excluded deleted photo. No ordinary-rendition aspect mismatch
remains. The only two remaining bounding-box warnings belong to that same
deleted photo; none remain on non-deleted photos.

- [Repair/backup verification](reports/photo-size-repair-verified-2026-10-28.json).
- [Post-repair all-row audit](reports/photo-dimensions-audit-2026-10-28-post-repair.json).

The findings below retain the pre-repair evidence and investigation history.

## Findings

| Finding | Photos | Evidence |
|---|---:|---|
| Photo-row and full-rendition dimensions agree exactly | 97,909 | Metadata comparison; includes the 192 smaller-rendition metadata errors below. |
| Full is an ordinary downscale with the same aspect | 4,162 | Expected for capped `full` renditions; copying full dimensions into these rows would lose the original coordinate space. |
| Photo-row width/height exactly reversed relative to full | 189 | 188 confirmed using actual full and ordinary image headers; one deleted photo's two URLs return 404. |
| Other photo/full aspect mismatch | 1 | Panorama row matches the exact original EXR; served images/DZI match an earlier render. Operator chose to align metadata with the uploaded artifacts. |
| No valid photo dimensions | 164 | 155 authorized and nine errored photos; not completed-photo repairs. |

There is a second, independent metadata problem in **192** of the exact-match
rows: all four ordinary numeric renditions have the opposite orientation in
their dimension metadata. The initial pass checked one ordinary rendition per
photo; the proposed-fix report subsequently checked the other three. All
**768 numeric rendition entries** are now confirmed reversed against their own
file headers. The full images and photo-row dimensions agree with the headers.

In total, **382 distinct photos** have dimension inconsistencies. The initial
pass checked **764 image headers** (full + one ordinary rendition per photo).
The proposal report adds 576 checks: **1,340 distinct image checks** altogether,
with 1,338 successes and two 404s belonging to the same deleted photo.

### Reversed photo rows

- 175 rows say 1440 × 2560 while full is 2560 × 1440.
- 14 rows say 2880 × 3840 while full is 3840 × 2880.
- 188 are non-deleted; one deleted photo (`a1600126-f947-416a-960f-ced19d371eb3`)
  could not be verified because its files are gone.
- 177 carry orientation `6`; 12 older November photos have no stored orientation.
- They were processed in November 2025 and March/April/May/July 2026.
- 66 have detections. All **135 boxes on 39 photos** previously reported as
  `bbox-exceeds-image` fit the full-image dimensions. This warning was measured
  against incorrect photo-row dimensions; it is not evidence of bad boxes.

The gallery now shows row/full/rendition dimensions separately, expands its
object list, shows original and rendition-scaled coordinates, and defaults the
overlay to full-image dimensions when those are an exact reversal of the row.
This is a viewer correction only.

### Reversed smaller-rendition metadata

All 192 photos carry orientation `8`, processed between
2025-12-06 12:51:56 UTC and 2026-02-02 07:34:36 UTC. All are non-deleted.
Examples of checked metadata versus actual headers:

| Recorded rendition dimensions | Actual file dimensions | Photos |
|---|---|---:|
| 1152 × 2048 | 2048 × 1152 | 187 |
| 768 × 1024 | 1024 × 768 | 3 |
| 1024 × 2048 | 2048 × 1024 | 2 |

The actual image files have the correct landscape aspect. This group needs
rendition metadata repairs, not rotated pixels or swapped photo-row dimensions.

### Panorama

Photo `42b675fc-a4ef-4ed7-a69f-d62a2d778bfc`, processed 2026-09-02:

- Photo row: **156,962 × 8,366**.
- Actual full image/header and full metadata: **8192 × 554**.
- Actual DZI descriptor and pyramid metadata: **157,180 × 10,646**.
- All six ordinary renditions agree with the full/DZI aspect, not the row.
- No detections are stored for this photo.

The DZI establishes the **rendered output** dimensions, not necessarily the
intended original source. Subsequent inspection of the archived EXR on
`ktiff.internal` found that the **photo row is correct for its exact source
bytes**. Both EXR windows are 156,962 × 8,366, and the file's MD5 matches the
photo row. The initial repair was withdrawn while that conflict was investigated.
The operator subsequently chose to **keep the uploaded artifacts** and align
the photo-row dimensions with their 157,180 × 10,646 coordinate space, without
reuploading. The current report reflects that explicit decision and retains the
original-source evidence. The operator applied that metadata repair to
production on 2026-10-28; the refreshed dump verifies the result. A standalone
[archive incident note](incidents/2026-09-02-panorama-stale-exr.md) preserves the
source/upload distinction and the recovered timeline.

#### Archived attempts and stale decoder cache

The five `uploaded/prod*` markers all point at the same source pathname, now
dangling because the work tree moved from `autocopy` to `autocopy_done`.
They do not preserve five EXR versions. The surviving per-run manifests clarify
what happened (all times below UTC, 2026-09-02):

| Time | Evidence |
|---|---|
| 08:35:31 | First manifest: worker failed to register the processing result with the API. |
| 08:47:58 | `prod` manifest: created photo `a9686561-9cf4-47b7-9c5e-750bf92b53af`. |
| 11:56:13, 12:03:03, 12:25:56 | `prod2`, `prod3`, `prod4`: duplicate responses, not three successful reprocesses. |
| 16:16:56 | Current EXR's modification time; header is 156,962 × 8,366. |
| 16:22:10 | Current archived DZI's modification time; also 156,962 × 8,366. |
| 17:19:03 | Current photo row's upload time. |
| 17:29:13 | Row completed; `prod5` manifest reports the current photo ID, and its marker follows within half a second. |

The pipeline log records the earlier render at **157,180 × 10,646**, then a
canvas rebase and rerender to **156,962 × 8,366**. The surviving EXR is
4,441,857,821 bytes; its MD5 `5a880e0b0c8f0eef7eb92b5e25d1509f` matches the
current row. Its archived DZI confirms the newer geometry. The served DZI and
all served renditions instead have the earlier geometry.

A synthetic test using the actual worker's `blur.read_image()` reproduces the
required split with libvips 8.16.1 and its default operation cache (100 entries):

1. Read a 30 × 20 EXR through the worker decoder.
2. Atomically replace that pathname with a 28 × 15 EXR, with a different mtime.
3. The worker's fresh OpenEXR probe returns **28 × 15**, but `read_image()`
   returns the cached **30 × 20** raster.
4. Disable the libvips operation cache in that isolated test process; decoding
   then returns **28 × 15**.

This mechanism fits the observed new-source row / old-render output without
requiring concurrent attempts. The worker's two dimension paths then preserve
the mismatch: rendition generation uses the cached raster dimensions, while
the processing response returns the fresh header dimensions. This is a
**reproduced bug and a strong explanation**, not proof of the historical cache
contents. The current remote worker container has been up only three days;
this investigation has not recovered the September processing logs.

Evidence is saved in
[the source-header record](reports/photo-dimensions-panorama-source-2026-10-27.jsonl),
`oneoff/scripts/2026-10-27_1800_inspect_remote_panorama.*`, and
`oneoff/scripts/2026-10-27_1830_probe_exr_path_cache.py` with its output.

#### Upload / reauthorization review

The source filename is an EXR panorama. The restored row records version 1,
upload time 2026-09-02 17:19:03 UTC and completion at 17:29:13 UTC. Version 1
does **not** exclude a retry: `authorize_upload()` reuses the photo ID for a
same-owner, same-MD5 row in `authorized` or `error` state without requiring a
version increase. It deletes and recreates that row with a new authorization
timestamp. A completed photo requires a higher requested version to reuse its ID.

Authorization accepts and stores **no image dimensions**. Completion assigns
`photos.width`, `photos.height`, and the entire `sizes` object together in one
transaction. Consequently an ordinary sequential reauthorization cannot retain
dimensions from the first authorization. Changing the actual input bytes would
also normally change the MD5 and therefore select a different photo ID.

There is a separate possible overlapping-attempt race: workers accept multiple
jobs for the same photo ID, and artifact destinations contain the owner/photo ID
but no authorization-generation identifier. A job writes its artifacts before
reporting completion. The completion endpoint returns success without updating
an already completed row; CDN/local artifact writes do not perform that row-state
check. API-streamed artifacts do check state and the current authorization's
signature before streaming, but do not hold that check through the write. Thus
overlapping attempts can potentially mix saved metadata and artifact bytes.
An old signature normally fails against a newly authorized row while that row
is still authorized (the signed timestamp changes), although the timestamp is
only second-resolution. This is a code-path possibility, **not evidence that it
happened to this photo**.

In this case the saved `sizes` dimensions already agree with the actual full
image and DZI. Merely overwriting files after an earlier completion would not
explain the mismatch *within the saved row*: the photo dimensions differ from
its own saved pyramid dimensions. The worker's discarded decoded dimensions
described below remain a more direct mechanism if the preliminary probe and
later raster read saw different dimensions. The original EXR has now been
verified; the stale decoder-cache reproduction above explains how the two
paths can disagree. Historical processing logs would be needed to confirm
that this was the mechanism on this upload.

These authorization/completion behaviors and the discarded-dimensions path are
present in historical tree `38052518` (2026-08-21), before this upload, as well as
the current source. This does not establish the deployed worker's exact commit.
A synthetic EXR with a 10 × 6 data window inside a 16 × 14 display window was
checked with the real worker: both OpenEXR probing and pyvips decoding returned
10 × 6. That test did **not** reproduce a data-window/display-window discrepancy.
The read-only row probe and synthetic fixture are saved under
`oneoff/scripts/2026-10-27_1710_review_panorama_source.py` and
`oneoff/scripts/2026-10-27_1700_probe_exr_window_dimensions.py`.

## What the existing fixer selected

`backend/scripts/fix_sizes.py` was introduced by `005e0d58` on 2025-12-05.
It selects only:

```text
sizes['320'].width > sizes['320'].height
AND sizes['full'].width < sizes['full'].height
```

That is **320 landscape / full portrait**. It trusts those metadata fields and
does not check image headers, photo-row dimensions, or the opposite discrepancy.
On this dump it selects **zero rows**.

There is also a defect in its generated SQL. With old full dimensions `w, h`,
it assigns `sizes.full = (h, w)` but `photos.width/height = (w, h)`. It fixes the
full metadata while leaving the row at the old orientation. That can create
the first inconsistency. Git/source establish this behavior, not whether the
script was actually run on every affected photo.

Do not reuse its output as a repair for the current sets without changing both
the selection and the assignments.

## Writer history and remaining work

- `77fc9947` (2025-12-03) changed small-rendition measurement to call
  `get_image_dimensions(output_file, source_orientation)`. That function swaps
  dimensions for orientations 5–8 even though it is measuring an output raster.
  This provides a mechanism matching the December–February orientation-8 group.
- `2654d74c` (2026-02-05) removes that resized-output probing path and records
  dimensions used to write the raster. The affected group's last processing
  date predates this change. Deployment identity per photo is not established.
- `cdb4e8d0` (2026-03-07) explicitly obtains actual decoded dimensions inside
  `create_optimized_sizes()`. This remains local to that method: the caller
  `process_uploaded_photo()` still returns its preliminary probe's width/height
  to the API. The API stores those returned values directly. That is a current
  path by which row dimensions and rendered/detection-space dimensions can differ.
- Metadata `orientation_code` may populate EXIF data used by the preliminary
  probe (`c079976f`, 2026-02-16); the raster loader reads/autorotates the image
  itself. This is a possible contributor, not a proven cause for each row.

Prepare repairs separately for photo rows, rendition metadata, and the panorama.
Use backed-up original values and per-row comparisons so later edits cannot be
overwritten. Confirm each rendition field against its own header before writing.
Ensure that reused local source paths cannot return an older libvips load.
Merely propagating the old raster's dimensions would hide a stale image upload.
**Implemented locally, 2026-10-28:** both worker input loaders now request
`revalidate=True`, the documented libvips per-load cache refresh. Five real EXR/
JPEG regressions fail before the patch and pass afterwards, including same-size,
same-mtime replacement and symlink retargeting. Global cache policy stays enabled.
The patch still needs worker deployment; the separate dimension-return refactor
below remains a follow-up.
Carry the actual decoded/pyramid source dimensions out of the worker rather
than inferring original dimensions from a capped full rendition. Preserve all
detected-object coordinates and flags during a metadata repair.

## Reproduction and artifacts

```sh
backend/.venv/bin/python scripts/audit_photo_dimensions.py \
  --database-url-env DATABASE_URL --source 'describe dump and date' \
  --output /tmp/photo-dimensions-audit.json \
  --anomalies-output /tmp/photo-dimensions-anomalies.jsonl

backend/.venv/bin/python -m pytest scripts/tests/test_audit_photo_dimensions.py -q
```

- [All-row metadata report](reports/photo-dimensions-audit-2026-10-27.json).
- [Image-header report](reports/photo-dimensions-header-check-2026-10-27.json).
- Suspect-row IDs/URLs and per-image check results are saved locally under
  gitignored `oneoff/photo-dimensions-*.jsonl`.
- The bounded header probe and private DZI check are saved in
  `oneoff/scripts/2026-10-27_1510_check_dimension_headers.py` and
  `oneoff/scripts/2026-10-27_1530_dimension_panorama_detail.py`.
- Header reads were capped at 64 KiB each; they parse dimensions without decoding
  image pixels. The WebP reader self-checks against Pillow-generated VP8/VP8L/VP8X
  fixtures. Its successful results agree with all checked full metadata and
  expose the 192 checked ordinary-metadata reversals.

The dimension audit's 13 focused tests pass. These checks do not clear the DB.

## Proposed-fix HTML report

`scripts/propose_photo_size_fixes.py` is a separate review tool. It reads the
saved audit and header/DZI evidence and writes an HTML report, a JSON proposal
plan, and reusable header checks. It has no database connection or apply mode.
Each photo has a preview and a link to `https://hillview.cz/photo/hillview-{id}`.
The report separates photo-row dimensions, smaller-rendition metadata, and the
panorama's source size; every field lists stored → proposed values and its own
evidence status. Missing/conflicting evidence remains explicitly visible.

```sh
backend/.venv/bin/python scripts/propose_photo_size_fixes.py \
  --anomalies oneoff/photo-dimensions-anomalies-2026-10-27.jsonl \
  --header-checks oneoff/photo-dimensions-image-headers-2026-10-27.jsonl \
  --dzi-evidence oneoff/scripts/2026-10-27_1530_dimension_panorama_detail.out.txt \
  --audit-report docs/reports/photo-dimensions-audit-2026-10-27.json \
  --source-evidence docs/reports/photo-dimensions-panorama-source-2026-10-27.jsonl \
  --match-uploaded-artifacts --check-images --output oneoff/size-fixes-report.html
```

`--check-images` fetches only missing header checks, each limited to 64 KiB.
Without that option the report is generated offline and unchecked proposals
stay marked as needing evidence. By default, panorama row corrections require
an original-source header agreeing with the DZI: a served DZI can describe an
older render. `--match-uploaded-artifacts` explicitly selects the uploaded
coordinate space, allowing a verified DZI proposal while preserving the source
disagreement in its evidence. That is the chosen basis for this repair.
`--source-evidence` accepts JSONL records with `id`, `dimensions: [width, height]`
and a `source` description. WebP checks use only the standard library;
JPEG/PNG additionally need Pillow. Use the generated `.headers.jsonl` as
`--header-checks` on subsequent runs to reuse all evidence. `--hillview-url`
can point the photo links at a different Hillview deployment.

The version 2 JSON plan records old values, per-field artifact URLs/dimensions,
source evidence, and the selected dimension basis.
[`scripts/fix_photo_sizes.py`](../scripts/fix_photo_sizes.py) checks those values
against a fresh DB snapshot, rechecks live headers before apply, and backs up
exact before/after metadata. The [repair runbook](photo-size-repair.md) covers
dry run, apply, verification and guarded restoration. The report generator
itself has no database connection or apply mode.

Generated output: `oneoff/size-fixes-report.html`, with sibling JSON plan and
header evidence. It contains **958 proposed dimension pairs** across 382 photos:
957 pairs for 381 photos are verified; the deleted photo with missing files
stays blocked. The groups are 189 photo-row swap candidates (188 verified), 192
sets of four rendition metadata swaps, and one panorama metadata adjustment to
match its uploaded DZI. The repair's read-only dry run against the restored
dump agreed with all 381 selected photos / 957 pairs. The operator subsequently
applied the generated SQL in production; post-repair verification is linked at
the top of this document.
