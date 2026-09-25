# Backfill photos.pitch from UserComment

## Current state

`photos.pitch` (double precision, alembic 032) is populated on **12,995** of 77,877 live
photos. Those came in through the `exif_data->'gps'` path: every row that has
`exif_data->'gps'->>'pitch'` also has the column set, and every row that has the column set
has that key. Nothing is missing from that source — measured 2026-09-25:

```
photos.pitch set                                    12,995
exif_data->'gps'->>'pitch' present                  12,995
pitch IS NULL AND exif gps.pitch present                 0   <- nothing to backfill here
```

## What is untapped

A **second, disjoint** population carries pitch in the capture app's provenance JSON —
`exif_data->'data'->>'UserComment'`, the same blob `_user_comment()` already parses for
`location_accuracy_m`:

```json
{"pitch": -84.25, "roll": -175.45}
```

```
UserComment contains "pitch"                         4,807
  ...of which photos.pitch IS NULL                   4,807   <- all of them
photos.pitch set AND no pitch in UserComment        12,995   <- the other population, entire
```

The two sets do not overlap at all, and neither do their owners (`0` owners in common).
They are two capture paths from two eras:

| set | n | owner | uploaded | pitch range |
|---|---|---|---|---|
| `exif_data->'gps'` → column | 12,995 | one | 2026-08-27 → 2026-09-15 | −89.6 … 87.1 |
| UserComment, **not** in the column | 4,807 | a different one | 2026-02-07 → 2026-09-01 | −89.9 … 87.7 |

So the second path was writing pitch into UserComment for months before the column existed,
and nothing ever moved it across. The overlap in DATES (Feb→Sep vs Aug→Sep) with no overlap in
OWNERS says this is about which client wrote the photo, not about when the column landed.

## Why it is worth doing

Pitch is not decoration for reconstruction. The solver has `--level_pitch_deg` and a level
prior, and the recon bench spent 2026-09-25 on a gauge problem where a camera's true pitch was
the thing being argued about; a frame whose pitch is known does not have to have it inferred.
4,807 frames is a third again on top of the 12,995 that already have it.

## The backfill

Straightforward, and safe to run more than once:

```sql
UPDATE photos
   SET pitch = ((exif_data->'data'->>'UserComment')::jsonb->>'pitch')::float
 WHERE deleted = false
   AND pitch IS NULL
   AND (exif_data->'data'->>'UserComment') LIKE '%pitch%';
```

Validity was checked before proposing it: all 4,807 parse as JSON, all 4,807 yield a float, and
**0** fall outside [−90, 90]. So no clamping or rejection logic is needed — but the WHERE clause
should still carry the range test rather than trust that, because the next batch of uploads is
not covered by a measurement taken today.

Do it as an alembic data migration rather than by hand, so it is recorded and so a fresh
database reaches the same state.

## The part that needs a decision

**Every one of the 4,807 also carries `roll`, and there is no column for it.** `photos` has
`compass_angle` and `pitch` and nothing else angular. Roll matters for the same reason pitch
does — a rolled camera's horizon is not level, and the recon bench has a `loss_horizon` term —
so the options are:

- add `roll double precision` beside `pitch` and backfill both in one migration;
- backfill pitch only and leave roll in the JSON, where nothing will read it;
- decide roll is not wanted and say so here, so the question is not re-opened.

Adding the column is the cheap moment: the migration that backfills pitch can add and fill roll
in the same pass, and doing it later means touching 4,807 rows twice.

## Also worth knowing

The capture path that writes UserComment should write BOTH — the column and the JSON — going
forward, or the same gap reopens for every photo uploaded after the backfill. Worth checking
which client writes `{"pitch", "roll"}` and whether it now also sets the column; if it does,
this is a one-off backfill, and if it does not, this document will be needed again.

## Relevant files

- `backend/api/app/photo_routes.py` — `_user_comment()`, the existing parser for this blob
- `backend/api/alembic/versions/` — 032 added `photos.pitch`
- the recon bench's consumers: `scripts/enrich/recon_params.py` (`level_pitch_deg`,
  `horizon_weight`), and `photos.pitch` is read into each run's frame manifest
