# Timestamp archeology — captured_at timezone dig

Status: **reference / findings + fix** · captured 2026-06-26 · companion to
[`pano-source-archaeology.md`](pano-source-archaeology.md) and the panorama backfill it grew out of.

> **Why this exists.** `photos.captured_at` drives the capture-time timeline walk
> (`GET /api/hillview/timeline`, keyset on `(effective_at, original_filename, id)`). A panorama
> backfill surfaced that Canon photos and phone photos were stored on **two different time scales**,
> so they interleaved wrong in the timeline (a panorama shot at noon sorted *after* a phone photo
> taken an hour later). This is the record of why, and of the one-shot fix — so nobody re-derives it
> or, worse, re-introduces it by re-running an old backfill.

## TL;DR

- `photos.captured_at` / `effective_at` are **naive UTC** (column is `DateTime(timezone=False)`;
  the migration-022 comment says "UTC timestamps without timezone").
- **Phone photos** got captured_at from their unix-ms timestamp → correct true UTC.
- **Canon EOS 5DS** photos got it from EXIF `DateTimeOriginal` via a worker bug that **stamped UTC
  onto a local wall-clock and discarded `OffsetTimeOriginal`** → stored shifted by the camera offset.
- The camera offset is a **manual, per-shooting-day setting, not DST**: `+01:00` (CET) from
  ~2026-02-10 to 2026-04-03, `+00:00` (UTC) from ~2026-04-05 on; Dec/Jan were `+00:00` too. You
  cannot infer it from the date — read the recorded offset.
- Fixed by a one-shot data migration (`backend/scripts/canon_captured_at_to_utc.sql`, applied to the
  **local** DB only) plus parser fixes in `worker/photo_processor.py` and
  `backend/scripts/backfill_captured_at.py`. **Prod not yet migrated.**

## The symptom

Two photos from 2026-03-28, true order pano-then-phone:

| file | true UTC | true local (+01:00) | stored captured_at | scale |
|---|---|---|---|---|
| `…036A0837---…0842.exr` (pano) | 12:19:50 | 13:19:50 | **13:19:50** | local wall-clock |
| `2026-03-28-14-19-41_photo_1774703981000_…jpg` | 13:19:41 | 14:19:41 | **13:19:41** | UTC |

Stored, the pano (13:19:50) sorts *after* the phone shot (13:19:41) — backwards. The phone unix-ms
`1774703981000` decodes to `2026-03-28 13:19:41 UTC`; the pano's first frame EXIF is
`13:19:50 +01:00` = `12:19:50 UTC`. The two are an hour apart on different scales.

## Root cause (in the code)

`worker/photo_processor.py::parse_exif_datetime` did, for any non-numeric EXIF datetime:

```python
return dt.replace(tzinfo=timezone.utc)   # stamps UTC on a wall-clock; ignores OffsetTimeOriginal
```

EXIF splits the instant across two tags: `DateTimeOriginal` is **always** naive wall-clock
(`YYYY:MM:DD HH:MM:SS` — verified: 3583/3583 offset-bearing rows are plain, 0 carry an embedded
offset/`T`/`Z`), and the zone lives only in `OffsetTimeOriginal`. Dropping the offset means the
wall-clock got relabelled UTC. Phone photos dodged this because they take the numeric/unix-ms branch
(`datetime.fromtimestamp(ts, tz=utc)`), which is genuinely UTC — and they carry no offset tag at all.

## What the EXIF actually says

Offset distribution across all non-deleted photos (`exif_data->'data'->>'OffsetTimeOriginal'`):

| offset | count | camera |
|---|--:|---|
| `+01:00` | 2085 | Canon EOS 5DS (all) |
| `+00:00` | 1498 | Canon EOS 5DS (all) |
| (none) | 26299 | phones + derived outputs |

Every offset-bearing row is a Canon EOS 5DS, so shifting only offset-bearing rows can never touch a
phone photo. The catch: ~877 Canon-derived rows (panoramas, stitched/`.tif` outputs) carry **no**
offset tag because they're not camera originals.

The offset by day, merged from DB tags + the 9460 disk `.meta.json` (`exif_dt` carries the offset),
is **consistent — one offset per day, no conflicts** — and shows a manual switch, not DST:

```
2025-12-30 +00:00   2026-02-07 +00:00   2026-02-10 .. 2026-04-03  +01:00   2026-04-05 onward +00:00
2026-01-01 +00:00
```

So the camera ran on CET (`+01:00`) through early April, then was set to UTC (`+00:00`) — summer
shots are `+00:00`, **not** `+02:00`, which is why date/DST inference is wrong and the recorded
offset must be used.

## The fix — data migration

`backend/scripts/canon_captured_at_to_utc.sql` — **2114 UPDATEs** (33 panoramas + 2081 frame shifts;
2357 already-UTC frames skipped as no-ops):

- For each Canon-derived photo: `captured_at_utc = wall_clock − offset`, where `offset` is the row's
  own EXIF tag, else the offset shared by other Canon frames that calendar day (the per-day map).
- Two pre-autocopy dates needed manual resolution: `2026-04-07` (`+00:00`, read via exiftool) and
  `2026-03-14` (boranovice — **no CR2 on disk**, so `+01:00` *inferred* from the surrounding era;
  this is the one value not read from a file). `2025-12-30` / `2026-01-01` confirmed `+00:00` by exiftool.
- Emitted as **absolute values keyed by `original_filename`** → idempotent and re-runnable (no
  double-shift), prod-portable (no row UUIDs, which differ between DBs). Filenames are unique among
  the change set (the only live duplicates are `+00:00` June `.tif`s, which don't shift).
- `effective_at` is recomputed by the migration-022 `BEFORE UPDATE` trigger automatically.

Generators live in the session scratchpad (`analyze_tz.py`, `gen_utc_migration.py`); the `.sql` is
the durable artifact. **Do not regenerate from post-migration data** — `wall_clock − offset` would
double-subtract.

Verified post-apply: the example pano lands at `12:19:50 UTC` (before the `13:19:41` phone shot),
March frames shift −1h, June/phone rows are unchanged, and panoramas interleave with their source
frames by frame number.

## The fix — ingestion (so it doesn't come back)

Both copies of `parse_exif_datetime` now take an offset and convert wall-clock→UTC
(`dt − OffsetTimeOriginal`), falling back to "assume UTC" when no offset is present (preserves the
phone/unix path):

- `worker/photo_processor.py` — `parse_exif_datetime(value, offset_value=None)` + `_parse_exif_offset`,
  call site passes `OffsetTimeOriginal` / `OffsetTimeDigitized` / `OffsetTime`.
- `backend/scripts/backfill_captured_at.py` — same fix. It had its **own buggy copy**; left
  unfixed, re-running it would overwrite the migration with wall-clock values again.

## How panorama captured_at is derived (context)

Panoramas (stitched EXR/TIF, `width > 10000`) carry no camera EXIF. Their captured_at is the **first
source frame's** time: the frame stem is embedded in `original_filename`
(`…_036A0819---…_036A0823.exr` → frame `036A0819`); sources live under `/d/shared/dev4/autocopy/`
(`.meta.json` `exif_dt`, else exiftool the `.CR2`), and the delivered-pano → source map is
`scripts/enrich/pano_map.md`. Two odd panos (`00.tiff`, `_36A7727 - _36A7738.webp`) have no dated
stem and were resolved via `pano_map.md`. The canon→UTC migration sets all 33.

## Filename-embedded capture stamps (phone / screenshot)

Phone and screenshot uploads are named `<localdatetime>_photo_<unixms>_<rand>.jpg` and
`<localdatetime>_capture_<unixms>.jpg`. The **`_photo_`/`_capture_` number is the capture epoch in
ms** (authoritative UTC); the leading datetime is just local wall-clock. Normally the worker sets
`captured_at` from client metadata that equals this stamp, but some uploads arrived with no
metadata → `captured_at` NULL → `effective_at` falls back to `uploaded_at`, so they sort by upload
order, not capture order (e.g. two shots 9 min apart uploaded on different days sorted backwards).

Validated against the 17940 stamped rows that already had `captured_at`: **17925 match the stamp
within 1s** (the column is whole-seconds, the stamp has ms — truncation, not disagreement). The only
>1s cases (15) are `_capture_` screenshots whose stored time is ~10–30s *after* the stamp; those
already have a value so they're untouched, and for NULL rows the stamp is still correctly ordered.

`backend/scripts/backfill_captured_at_from_filename.sql` fills the **922** NULL-`captured_at` rows
that carry a stamp, computing `to_timestamp(ms/1000) AT TIME ZONE 'UTC'` from the filename in-DB —
self-contained, prod-portable, idempotent (guarded on `captured_at IS NULL`). Applied to the
**local** DB. The worker does **not** parse the filename as a fallback, so new metadata-less uploads
can still land NULL.

## Open items

- **Neither migration applied to prod.** Run, when ready (both idempotent / safe to re-run):
  `backend/scripts/canon_captured_at_to_utc.sql` and `backend/scripts/backfill_captured_at_from_filename.sql`.
- **6374** photos still have `captured_at` NULL with no stamp and no EXIF — nothing more exact exists
  in them; they remain on the `uploaded_at` fallback.
- The `2026-03-14` offset is inferred, not read — revisit if those boranovice frames' originals resurface.
- Optional: teach the worker to fall back to the filename `_photo_/_capture_` stamp so future
  metadata-less uploads don't land NULL.
