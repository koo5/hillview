# Migrate `Photo.detected_objects` to one format (prod)

**Status:** parked plan, ready to hand to an agent. Written 2026-09-20 at the operator's request:
*"i should probably eventually clean this mess up in the prod hillview db, migrate every photo to
the newest format, after some eyeballing."*

**Where the authority lives:** `backend/common/detections.py` (added upstream 2026-09-20,
commit `df422d72`). It defines `BLUR_CONFIDENCE = 0.4`, `should_blur()`, `is_blurred()` and
`blurred_only()`, and its module comment is the canonical description of the four formats. Read it
first; everything below assumes it.

## Why this is worth doing

Four shapes of `detected_objects` coexist in the DB, so **every consumer has to carry the reading
rule** — the worker, the API, and (until 2026-09-20) the enrichment workbench twice over. A
consumer that gets it wrong either masks pixels that are fine or, worse, treats a blurred face as
ordinary image data. One format means `obj["blurred"]` is simply true or false and the rule can be
deleted from everywhere except the writer.

It also unblocks the workbench cleanly: enrich now asks the public endpoint for the rectangles
(`GET /photos/{id}/detections`, uncredentialed, `scope: "blurred"`) instead of re-deriving them,
and that endpoint is only as trustworthy as the column behind it.

## The four formats, and where they actually fall in time

Measured on the workbench's `photo_mirror` (which lags prod slightly), photos by capture month
carrying at least one object of each shape — a month can appear in two columns:

| capture month | no confidence (#1) | has confidence (#1b/#2) | explicit `blurred` (#2/#3) |
|---|---|---|---|
| 2025-09 … 2026-03 | 6 → 2087 a month | 0 | 0 |
| 2026-04 | 2837 | 5 | 4 |
| 2026-05 | 1069 | 282 | 3 |
| 2026-06 | 505 | 1381 | 597 |
| 2026-07 | **0** | 3352 | 2746 |
| 2026-08 | 0 | 3443 | 2885 |
| 2026-09 | 0 | 1952 | 1691 |

So the cutover runs 2026-04 → 2026-06 and is complete by July. Everything captured before that is
format #1: **no confidence stored at all**, which `should_blur()` treats as always-blurred.

## The hard part, stated honestly

For format #1 there is no confidence to migrate and **no way to recover one**: the image on disk is
already blurred, so re-running the detector on it finds nothing where a face used to be. The
operator's own note: older photos went through several blurring approaches before doodles, so the
stored rectangles are not guaranteed to match what the pixels actually show.

Therefore this migration must **not** invent confidences. It can only:
1. write the explicit `blurred` flag that `should_blur()` already derives, and
2. record, per object, that the flag was *derived* rather than *observed*.

Anything more requires looking at the pixels — which is what the eyeballing step is for.

## Suggested shape of the work

1. **Inventory, in prod, before touching anything.** Count photos per format, per month, per
   `model_name`, and count objects whose `bbox` is malformed or out of bounds. Publish the numbers
   in the PR/ticket; they are the before-picture.
2. **Pre-screen the pixels instead of eyeballing everything.** For a sample of format #1 photos,
   measure the blur inside each recorded box against a ring just outside it (Laplacian variance, or
   the gradient-energy ratio). A genuinely blurred box is much smoother than its surroundings. Sort
   by that ratio: the ambiguous tail is what a human should actually look at, and it is a small
   fraction of the corpus. **Do not** decide anything automatically from this — it is a triage aid.
3. **Eyeball the tail**, with the boxes drawn on the image, a screenful at a time. What you are
   answering is one question per photo: *are these rectangles where the blurring actually is?*
4. **Write the migration** as an idempotent, resumable batch (by id range or by `updated_at`
   cursor), in a transaction per batch, with `--dry-run` printing the exact counts it would change:
   - objects that already have `blurred`: untouched;
   - objects with a confidence and no flag (#1b): `blurred = confidence >= BLUR_CONFIDENCE`;
   - objects with neither (#1): `blurred = true`, plus a provenance key on the object (for example
     `"blurred_from": "legacy-no-confidence"`) so the guess stays visible forever;
   - manual overrides (#3): already `blurred: true`; leave them, keep `manual`.
   Never rewrite `bbox` coordinates, `class_id`, or the container's `model_name`.
5. **Back up first** — a dump of `id, detected_objects` for every row the batch will touch, kept
   until the verification below passes. This column is not reconstructible.
6. **Verify by behaviour, not by inspection:** for a random sample of a few thousand photos,
   `blurred_only(old) == blurred_only(new)` must hold exactly. The migration is a *representation*
   change; if any consumer would see different rectangles, it is wrong.
7. **Then delete the rule from the consumers**: `should_blur()`'s legacy branch, the workbench's two
   copies of `BLUR_CONFIDENCE` (`enrich/api/app/routers/recon.py`, `scripts/enrich/reconstruct.py`,
   pinned together by `scripts/enrich/recon_anon_check.py`), and any other re-derivation. That
   deletion is the point of the exercise; a migration that leaves every consumer still guessing has
   bought nothing.

## Things that will bite

- **The workbench mirror is not prod.** It syncs from the dev DB and lags. Take the inventory in
  prod.
- **`detected_objects` is JSONB with a container plus an `objects` array.** The container's own keys
  (`model_name`, `manual`) describe the pass, not its subjects — carry them through untouched.
- **Sub-threshold detections are a privacy surface.** Boxes recorded but deliberately left visible
  are an index of people the detector saw and the pipeline chose not to blur. They stay in the
  column (the owner and moderators need them to re-tune the threshold) but must never widen the
  public response — `blurred_only()` is what enforces that, and the migration must not disturb it.
- **Uploaders can disable anonymisation per photo.** A photo with no boxes may be deliberate, not
  missing data. Do not "fix" it.
- **Re-detection is not a migration.** Running the detector again on already-blurred images finds
  less than what is recorded, not more. If re-detection is ever wanted it belongs on the ORIGINALS,
  as a separate decision with its own retention questions.

## Done when

One format in prod; `blurred_only()` returns identical rectangles for a large sample before and
after; the legacy branch of `should_blur()` and every consumer-side copy of the rule are deleted;
and the inventory numbers are re-run to show the before and after.
