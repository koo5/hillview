# The LLM photo analyzer: what it is, what state it is in, and what to point it at

Written 2026-09-08, when the question came up as "will the photo analysis service be of
any use" for 3-D modelling. Short answer: the *skeleton* is right and worth reviving, the
*question it asks* is not the one 3-D work needs, and the richest thing it already
computed is being thrown away at the database boundary.

## What it is

`scripts/analyzer/` — its own git repo, **not tracked by the hillview repo** and with the
containerisation still uncommitted inside it. Two entry points:

- `analyze_photo.py` — the library: OpenRouter call, JSON schema, focal-length distance
  hints.
- `analyzer.py` — the service loop: poll Postgres for a photo with `analysis IS NULL`,
  `processing_status='completed'`, `deleted=false`, `FOR UPDATE SKIP LOCKED`; analyse;
  write back.

Each photo gets **two** calls: a "features" pass and a "distances" pass. Results are cached
as one JSON file per `file_md5` in `$ANALYZER_DATA_DIR`, holding the full request and the
parsed answer, so a rerun costs nothing.

## The two questions that were open

**Does the containerised analyzer reuse the data files as-is?** Yes, and the volume was
seeded. `hillview_analyzer_data` holds 44,776 files: 44,690 copied in dated Jun 15, plus 86
(43 photos) written Jul 10 21:29–21:30, which is the container actually running for a
minute or two. `docker compose --profile analyzer up -d --build analyzer` is the launch;
`hillview_analyzer` currently sits in `Created`, never started since.

**Was it given a database with an unrun migration?** No — there is no analyzer database.
It writes `photos.analysis` (JSONB) in the main Hillview Postgres, a column that already
exists in `backend/common/models.py` and in the live table. Nothing to migrate.

**But the seeded volume is stale.** `/shared/analyzer_data` — the production copy, which
the un-containerised script was writing until it stopped — holds **26,180** photos with
files as recent as 2026-08-06. The container's volume holds 22,388, from Jun 15. Reviving
as-is would re-pay for roughly 3,800 photos. Re-seed the volume from `/shared/analyzer_data`
first.

## Coverage is the inverse of what 3-D work needs

31,328 of 70,959 photos carry an `analysis`. The gap is not random — it is *recent*:

| month uploaded | photos | analysed |
| --- | --- | --- |
| 2026-05 | 2,308 | 2,308 |
| 2026-06 | 8,561 | 5,368 |
| 2026-07 | 14,233 | 1,712 |
| 2026-08 | 20,418 | 171 |
| 2026-09 | 3,399 | 0 |

The dense low-interval shooting started exactly where the analyzer stopped. The two spots
picked for reconstruction: spot A (Vyšehrad plaza) has 5 of 51 analysed; spot B (Prosek)
218 of 407. **The photos we most want to reason about are the ones it never saw.**

The `640_llm` derivative — the size it feeds the model — exists for 100 % of 2026-08 and
2026-09 uploads, so nothing else is blocking a restart.

## The best layer it produced never reaches the database

The cached sessions carry `description`, `objects` (a free-text list), `has_horizon`,
`buildings_on_horizon` and `signs_or_writing`. `distill_sessions` keeps `description` but
never `objects`; `analyzer.py` then filters the distilled dict down to eight keys before
writing, and `description` is not among them. So the DB holds tags and distances, and the
prose is on disk only.

Scale of what is sitting there unused: **21,598 photos with a description and an object
list, 6,944 distinct object strings**, most common `trees` (15,203), `sky` (8,304),
`grass` (6,211), `clouds`, `street`, `buildings`, `road`, `hill`, `path`, `lamp post`.
A re-import pass over the existing cache would add that layer for zero API calls.

## Is the existing schema useful for 3-D?

Weakly, and not where it matters.

`closest_object_distance` does stratify per-frame reprojection error on `walk_jizni`
(<3 m → 7.5 px median, 3–10 m → 14.1 px, ≥10 m → 140.9 px), and `visibility_distance`
"near" frames are ~4× worse than "medium". But the single most common value in the whole
corpus is 7.5 m (6,376 photos), and it shows up on both the best and the worst frames —
it reads like a default answer, not a measurement. Don't build a gate on it.

What 3-D actually needs is not in the schema at all: **permanent vs transient** (facade,
kerb, pole, ground versus foliage, vehicles, people, snow, scaffolding), sky, glass and
other specular surfaces, and a usable/unusable verdict per frame. That is a prompt change,
not a model change.

## Prompt engineering and evaluation

There is specialised tooling for this, and we can also just run our own benchmarks — and
here that is the better deal, because the task is ours and the gold data is ours: the 457
hand-drawn annotations across 42 photos, and now an *objective downstream metric*, the
per-frame reprojection error out of the recon bench. A label scheme is good if masking by
it improves a solve.

One thing that is **not** free: cross-model comparison. Of 26,180 cached photos, exactly
**3** were analysed by more than one model — the corpus is single-model per photo
(nemotron-nano-12b-v2-vl 35,183 sessions, qwen3-vl-30b-a3b-thinking 17,649, each in its own
date range). Any model comparison needs fresh runs on a shared subset.

Also note `find_duplicate` matches on model **and** prompt **and** temperature, so changing
either re-analyses everything. That is correct behaviour, but it means a prompt revision is
a full re-run; size the subset accordingly. `distill_sessions` merges across sessions
preferring the most recent success, so mixing models in the cache is safe.

Free vision models are available on OpenRouter again (checked 2026-09-08): `google/gemma-4-31b-it:free`,
`google/gemma-4-26b-a4b-it:free`, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`,
`thinkingmachines/inkling:free`, `nex-agi/nex-n2.5-pro:free`.

## Recommendation

Revive it, but re-point it.

1. Re-seed `hillview_analyzer_data` from `/shared/analyzer_data` so the 3,800 photos
   production already paid for are not paid for twice.
2. Commit `scripts/analyzer/` into the repo, or vendor the container build. Right now the
   only copy of the containerisation is uncommitted in a nested git repo.
3. Re-import the existing 26,180 cache files with a distiller that keeps `description`,
   `objects` and `has_horizon`. Zero API cost, 21.6 k photos gain a semantic layer.
4. Add a third pass with a **geometry-facing** schema — permanent/transient, sky fraction,
   specular fraction, texture verdict, frame-usable-for-SfM — and benchmark schema
   variants against per-frame reprojection error on a bench cluster, not against taste.
5. Only then backfill the 39 k unanalysed photos, newest first, since those are the dense
   spots.
