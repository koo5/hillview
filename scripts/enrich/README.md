# enrich — vision/enrichment subsystem (experiments)

Sibling to `scripts/analyzer/`. Implements the techniques and recipes in
[`docs/vision-subsystem.md`](../../docs/vision-subsystem.md). Greenfield / experimental.

## Conventions

- **Deps via `uv`, pinned for reproducibility:**
  `uv tool install --exclude-newer "$(date -d '6 weeks ago' +%F)" <pkg>` (likewise for any
  experiment venv). Keeps the fast-moving CV stack stable across runs.
- **Outputs are self-contained HTML reports** (open in a browser) — crops, candidate matches,
  maps, residual plots — not just console logs.
- **Read-only** against the data export / main DB; never mutates Hillview data.
- **Data source** is `photos.csv` / `photo_annotations.csv` (currently `~/hggg`; a fresh prod dump
  is incoming). Every script takes `--data` so the source is swappable.
- **Geocoding**: no local Nominatim — use a Nominatim/Photon `/search` (forward, `geocode-fwd`) or
  `/reverse` (the existing `backend/api/app/backfill_places.py` pattern, `osm-reverse`). Public OSM
  is acceptable for *small* calibration runs only; self-host for bulk.

## Pano source mapping (delivered pano → upstream `.pto`/`.exr`)

- **`pano_map.py` → `pano_map.md`** — canonical map: joins every delivered Hillview pano to its
  pics source by frame-code token + crop-dims; catalogs the `hugin/` hand-stitch tree; lists
  untapped workdirs. `python scripts/enrich/pano_map.py`.
- **`match_autocopy.py`** — diagnostic matcher (prod-manifest / filename / dims+geo; flags
  re-stitch drift).
- Full findings & the five-pipeline-generation map: [`docs/pano-source-archaeology.md`](../../docs/pano-source-archaeology.md).

## Pipeline (recipe R2 — design doc §6–§7)

1. **`r2_select_and_gate.py` — M1-0 feasibility ✅ (CPU/CSV, stdlib only).**
   Picks clean single-frame targets, lists POIs, checks the corpus has co-visible/near candidates.
   `python scripts/enrich/r2_select_and_gate.py --data ~/hggg`
   → 11/11 targets have abundant candidates; matching has plenty to work with.

2. **`r2_calibrate.py` — M1-1 pano geometry calibration (next).**
   Target pano: `333e8851-c59b-4133-bce5-2d1ddc2ce335`. Derive each POI's bearing
   (center-bearing + FOV·x, projection-aware), `geocode-fwd` the clean labels, **`fit-calibration`**
   the effective FOV/projection/bias, emit an **HTML report** of derived-vs-true bearing residuals
   across the pano width. Answers: is the bearing systematically fixable, and is the delivered
   angular model usable without the `.pto`? (FOV/projection are *fit from the anchors* — the `.pto`
   is ground truth but not strictly required for this probe.)

3. **`r2_match.py` — M1-2 feature-match + localize.**
   Fetch the frame's `full` pixels + candidates, run **LightGlue** (uv-pinned; MASt3R fallback),
   keep geometrically-consistent matches, then `proximity-transfer`/`triangulate` → `location`.
   HTML report of matches + located POIs. Needs network (image URLs) + the matcher dep.

4. **naming.** `geocode-fwd` / `osm-reverse` + LLM toponym match → label; compare to gold.
