# Terrain overlay graduation — design & plan

Status: **built and verified end to end 2026-08-07** (uncommitted). This is
the design record for promoting the per-photo terrain overlay — the fitted
horizon line + peak labels from the workbench's `/terrain/overlay` bench —
into the main app's zoom view, plus the depth buffer that makes any pixel
answer "what am I looking at?".

The mechanism works; the open questions are all about the LABEL POOL —
what counts as visible, and at what tolerance (see below). Companion docs:
`terrain-mode.md` (the mode, the open "artifact graduation" item this
partially discharges), `terrain-data-licensing.md` (the obligations that
travel with the data).

## What the overlay actually is

Three layers, wildly different weights:

1. **The fit** — the only thing the curator authors. One canonical-JSON
   literal saved as the `hv:terrainOverlayFit` fact
   (`enrich/api/app/routers/terrain.py`, `_overlay_fit_json`):
   `{projection, centre_bearing, fov_deg, horizon_pct, v_scale, roll_deg,
   warp[2–9], visibility_km}`. Measured: **164–203 bytes**.
2. **The depth wedge** — the render's uint16 buffer. The horizon line is
   *derived, never stored*: per column, binary-search the depth column for
   the first hit within the visibility cutoff → elevation angle → project
   into photo pixels through the fit. Measured (photo-wedge renders,
   typically ~4000×700 @ 0.025°): 7.7 MB raw median, **117 KB gzipped
   median**, 489 KB max — smooth quantized depth compresses ~60:1.
3. **The labels** — Overpass peaks ∪ towers (ODbL); visibility, occlusion
   and distance filtering all decided from the same depth buffer.

So the overlay ≈ a depth map plus a 200-byte calibration. Everything except
the fit and the label names is a function of (depth, fit, visibility_km).

**Fog is already one value.** In this bench `visibility_km` is a single
per-fit scalar — a hard distance cutoff on skyline extraction and label
filtering, not shading. (The per-pixel Koschmieder fog lives only in the
shared panorama viewer's shader; the overlay page never uses it.) Fixating
fog therefore costs nothing: it's fixated by construction, and it is what
lets the export bake the overlay to vectors and drop depth entirely.

## Two layers, different jobs

The graduated overlay carries **both** a baked skyline and the depth buffer,
because they answer different questions:

| layer | what it buys | cost | when fetched |
|---|---|---|---|
| **baked skyline** (JSON) | the horizon draws *instantly*; the exact curve the curator approved | 3–4 KB gz (measured) | with the overlay |
| **depth buffer** (referenced file) | click *anywhere* — hillside, field, ridge below the skyline → coordinates | 117 KB gz median, 126 KB measured | lazily, on first click |

The skyline is not made redundant by the depth. It exists so the client
never has to fetch and decode megabytes before it can draw a line, never
re-runs the O(W×H) column scan per fog stop, and always renders exactly what
was reviewed — even if the depth artifact is missing. The depth is purely
the *interaction* layer.

Measured on a real photo-wedge render (4152×690, ČÚZK+GLO30 stack):

| payload | raw | gzipped |
|---|---|---|
| fit | ~0.2 KB | — |
| skyline: elevation + distance per azimuth sample (4152 samples) | 59 KB | **3.4 KB** |
| labels, ~30–100 × `{name, lat, lon, ele, distance_m, azimuth}` | 5–12 KB | ~2 KB |
| render ref + depth grid descriptor + attribution | ~1 KB | — |
| **document total** | **~60 KB** | **~4–6 KB** |
| depth buffer (separate file, pre-gzipped) | 5.7 MB | **126 KB** |

**CBOR: rejected.** At document sizes gzipped JSON already wins, and CBOR
costs `jq`-ability across the whole review chain. The heavy thing is the
depth buffer, and it is not JSON at all — it stays raw uint16, stored as a
file, referenced by URL.

## How the depth buffer travels

The package is one JSON file the operator drops into hillview's admin, so
the bytes ride along **base64 in a top-level `blobs` map**, keyed by the
sha256 of the stored (gzipped) bytes, with ops referencing the hash:

```json
{"ops":  [{"op": "set_terrain_overlay", …,
           "overlay": {…, "depth": {"blob": "<sha256>", "width": 4152, …}}}],
 "blobs": {"<sha256>": {"encoding": "gzip+base64", "bytes": 126000, "data": "H4sIA…"}}}
```

Content-addressing means two photos fitted against the same render share one
blob, and re-applying a package is a no-op. On apply, hillview verifies the
hash, writes the bytes to the write pool as
`terrain/<sha256>.depth.bin.gz` (served with `Content-Encoding: gzip`,
exactly like the workbench's own artifacts), and rewrites the reference to a
URL — mirroring how DZI pyramids already live in a pool with a descriptor on
the row. Keeping blobs out of the ops keeps the manifest readable and
diffable.

**Known gaps**:

* Blobs are deliberately *not* deleted when a photo is deleted — being
  content-addressed, they are shared, and per-photo deletion cannot tell
  whether it holds the last reference. Reclaiming them means an offline
  sweep (list `terrain/*.depth.bin.gz`, subtract every URL still referenced
  by a non-deleted photo). At ~126 KB per render the leak is small and
  bounded by the number of curated overlays.
* The admin package list parses each incoming file whole to read its header,
  which now means parsing the base64 blobs too (~170 KB per distinct
  render). Bounded in practice — packages leave the incoming dir once fully
  applied — but if many large packages ever queue up, move blobs to sidecar
  files next to the manifest rather than parsing more cleverly.

## Two comparisons, deliberately different

It is easy to conflate these; they answer different questions.

* **The workbench's "landed"** compares the **fit alone**, so a re-render or
  a hillview-side horizon nudge never resurrects a settled item.
* **Hillview's "already applied"** compares the **whole document** (minus
  `user_adjust`, and with the depth reference reduced to its content hash,
  since it is a `blob` before apply and a pool URL after). Comparing only the
  fit there would mean an overlay re-rendered from a better elevation model —
  same alignment, better skyline — could never be published without
  artificially perturbing the fit.
* **The conflict precondition** stays a question about the fit: has
  hillview's alignment moved since the workbench last looked?

## The attribution is an invariant

`build_overlay` **refuses** to bake an overlay whose render carries no
attribution. The worker's `TERRAIN_ATTRIBUTION` defaults to empty and it only
writes the key when set, so an unconfigured worker produces renders with no
notice — and graduation is precisely the step that would publish those to
real visitors, where the viewer's show-it-if-present check would display
nothing at all. Failing at bake time keeps the licence obligation a property
of the data rather than a habit. Such photos are reported back to the
operator in the export response (`skipped`), never silently dropped.

## The pipeline, end to end

**Toggle = approval, not a new flag.** The workbench idiom is "the
/graduation review IS the selection": items derive from *approved facts*
vs. the mirror. The overlay page already receives `approved` from
`GET /terrain/overlay-fit`; the toggle calls the generic
`POST /api/facts/curate {fact, decision}` on the fit fact. "Approved beats
newer" restore precedence already exists server-side.

**Export op** — a fourth op kind in `enrich/api/app/routers/graduation.py`
alongside `set_annotation_body` / `create_annotation` /
`set_annotation_target`:

```json
{"op": "set_terrain_overlay", "photo_id": "…",
 "overlay": {"version": 1, "fit": {…}, "skyline": […], "labels": […],
             "render": {"id": "…", "meta": {…}}, "attribution": "…",
             "label_attribution": "peaks © OpenStreetMap contributors"},
 "precondition": {"fit": "<mirrored canonical fit JSON or null>"},
 "facts": ["…/id/fact/…"], "summary": "terrain overlay (horizon + N labels)"}
```

Rides the existing package (`hillview-enrichment`, provenance TriG, browser
file download → `backend/data/graduation/incoming`).

**Extraction runs server-side (Python).** The bench's `skylineFor()` is
page-local TypeScript, but export must not depend on a browser session
holding depth in memory. The extraction is ~10 lines of numpy
(`renderer.py` has `decode_depth_u16`; the cut is a `searchsorted` per
column), and the peaks pool is already a server endpoint. Label
*selection* (prominence thinning) stays client-side at draw time — it is
display-dependent; the export ships the visible candidate set. `render_id`
comes from the fit's run params (`kind='overlay_fit'`), falling back to the
newest done render for the photo.

**Hillview storage: `photos.terrain_overlay` JSONB** (migration 030, head
is 029_share_links). Column, not sidecar table, because:

- KB-scale JSON on the row is accepted precedent (`detected_objects` is
  documented "KBs per photo"; `exif_data`, `analysis`, `geocode`);
- every list endpoint curates fields explicitly, so the column is invisible
  to all existing responses;
- decisive: the sync mirror copies *columns* (`PHOTO_JSON` in
  `enrich/api/app/sync.py`), so landed-detection is a one-line change; a
  sidecar table would need a whole new mirror + reconcile pass.

Served lazily via `GET /api/photos/{id}/terrain-overlay` with a
column-scoped select, cloned from the `/detections` endpoint
(`photo_routes.py`), public-or-owner visibility.

**Apply**: a new branch in the existing admin graduation routes
(`backend/api/app/graduation_routes.py`, `require_admin()`): preview shows
the overlay summary + attribution; apply sets the column; archive when all
ops reflected. Precondition check compares the mirrored canonical fit
(conflict surfacing, same spirit as the rect precondition).

**Loop closure (workbench stops showing it).** Add `terrain_overlay` to the
mirrored photo columns; the suggestions query compares each approved fit
fact's canonical JSON against `photo_mirror.terrain_overlay->'fit'` — equal
⇒ `landed`. Observation, not acknowledgement, exactly like the three
existing op types.

**Future zoomview editability without un-landing.** The stored object keeps
`fit` verbatim-canonical; any hillview-side nudge (horizon fine-tune) goes
in a separate `user_adjust` field (e.g. `{horizon_pct_delta}`). The
workbench comparison reads only `.fit`, so a zoomview edit can never
resurrect the item as pending — and the adjustment flows back through the
ordinary photo mirror, where the bench could someday import it as a draft.

## Drawing in zoomview

- Move the projection math (equirect/cylindrical/rectilinear + warp +
  roll-shear) and `skylineFor` types out of the bench page into
  `shared/terrain/overlayFit.ts` — both apps already alias
  `$terrain → shared/terrain`, and the bench imports back from shared so
  there is one implementation.
- Skyline paints on a sibling canvas in the OSD container, cloned from the
  edge-label canvas pattern (`OpenSeadragonViewer.svelte`: absolute,
  pointer-events none, z-index 2, rAF-coalesced repaint on
  `viewport-change`/`update-viewport`).
- Peak labels paint through the unchanged zoomview label layouter — already
  the decided v2 approach in `terrain-mode.md`.
- Visibility toggle: a `showTerrainOverlay` localStorage-shared store,
  same pattern as `showDetections`; overlay fetched lazily on
  `photo_id` when toggled on.

## Licensing thread

- `attribution` (from the render's meta — the worker stamps
  `TERRAIN_ATTRIBUTION` per DEM stack) is a **mandatory field** of the
  overlay item, copied at export and stored in the column. Old overlays
  keep the notice that was true when rendered.
- `label_attribution` is separate ("peaks © OpenStreetMap contributors") so
  toggling labels toggles the credit.
- Display: a row in `PhotoInfoWindow` (already shows License/By/Source in
  zoomview) and/or a statusbar line like `TerrainPane`'s
  `terrain-attribution`, shown whenever the overlay layer is on.
- **6(c) tripwire**: photo pages are public, so the first shipped overlay
  is the "communication to the public" moment — the Copernicus liability
  sentence must land on the app's terms/legal page **in the same release**
  (see `terrain-data-licensing.md`, checklist row 2).
- The admin graduation preview displays the attribution so the reviewer
  sees the obligation travel with the data.

## Click-anywhere: the geometry

`shared/terrain/overlayFit.ts` carries the fit's projection **and its
inverse**, so both apps agree to the pixel:

- `project(azimuth, elevation) → (x, y)` draws the skyline and anchors labels;
- `unproject(x, y) → (azimuth, elevation)` is the click-back — analytic in
  all three projections (equirect / cylindrical / rectilinear), no search;
- `pickFromOverlay(overlay, depth, x, y, W, H)` composes it: unproject →
  grid cell → the distance the horizon march already computed → forward
  geodesic → lat/lon. A click above the skyline snaps *down* the column to
  the horizon, so tapping sky near a ridge still answers.

The round trip is unit-tested at 1e-6° across all three projections; a 1°
error would put a "click a mountain" answer on the wrong mountain.

## Slices

1. ✅ Extract `shared/terrain/overlayFit.ts` (projection math, inverse,
   skyline extraction, document types); declare `hv:terrainOverlayFit` /
   `hv:terrainOverlayDraft` in `enrich/vocab/hv.ttl`.
2. ✅ Overlay-page "graduate" toggle → `POST /terrain/overlay-fit/graduate`
   (approves the fact; demotes the previously approved one so there is
   exactly one approved fit per photo).
3. ✅ Python skyline extraction + label projection + `set_terrain_overlay`
   export op + depth blobs in the package.
4. ✅ Backend: migration 030 (`photos.terrain_overlay` JSONB), apply branch
   with blob storage, `GET /api/photos/{id}/terrain-overlay`.
5. ✅ Sync: mirror the column; graduation page grows an overlays section
   with landed-by-comparison; hillview's admin review page renders overlay
   ops (selected by photo, since they belong to no annotation) and shows
   the attribution the reviewer is about to start publishing.
6. ✅ Frontend: zoomview skyline canvas (z-index 1, under annotation
   labels) + labels via the sky layouter + lazy depth fetch on click +
   attribution line + legal-page 6(c) sentence.
7. Later: `user_adjust` fine-tuning UI; a fog slider in zoomview (the depth
   is there, so this is now just UI); offline blob sweeper.

## Verified

Unit-tested: the projection and its inverse (round-trip to 1e-6° in all
three projections), skyline extraction against the bench's semantics
(including near-clip zeros and fog cutoffs), label occlusion/priority,
click-back including sky-snap and local horizon nudges, depth-cache
sharing and size validation, blob hash verification, and the two
comparisons below.

**Full loop run live, 2026-08-07**, photo 17eaaceb (Hvězdárna Ďáblice →
sever, 77908×4111, rectilinear fov 93.8°) against render 252a7ea8
(4152×690, ČÚZK+GLO30):

| step | result |
|---|---|
| approve fit → workbench suggestions | 1 pending overlay |
| export | 343 KB package, 18 s, 4152/4152 skyline samples, 667 labels, 128 700 B blob |
| hillview admin preview | `clean`, provenance TriG parsed, attribution surfaced |
| apply | column written, blob filed, package archived |
| blob integrity | sha256 identical to the workbench artifact; decodes to exactly 4152×690 |
| re-preview / re-apply | `already_applied`, refused (confirms the blob→URL normalization) |
| sync | moved to `overlays_landed` |
| stored size | 190 KB raw → **37 KB** in the JSONB column |
| served | `GET /photos/{id}/terrain-overlay` 166 KB raw / 24 KB gz |

**Click-back at the photo's real geometry**: round-tripping labels through
project → unproject → depth lookup returns each peak's own coordinates to
within **40–187 m at 52–80 km** — the expected residue of 0.025° columns
and 4 m depth quanta. Arbitrary clicks behave correctly (horizon → 85 km,
above-horizon → snaps down, below-horizon → 1.8 km near field).

Test fixtures (a stub photo + admin user, needed because hillview's DB had
just been purged) were removed afterwards, and the mirror row they clobbered
was restored from `/shared/photos_5.csv`.

## The label pool: what it contains, and the tolerance question

Measured on render 252a7ea8 (photo 17eaaceb, Ďáblice → north): 4152 × 690,
0.025° per column AND per row, max distance 200 km; candidate pool
`/terrain/peaks` r = 200 km = 41 461 features, of which 8 459 fall inside
the sweep and the distance gates. Probes: `oneoff/scripts/2026-08-16_08*`.

### How the scan decides visibility — and where the tolerance enters

`projectPeak` (peakLabels.ts) / `project_labels` (overlay_export.py) walk
the peak's column top-down. Below the skyline a column's depth is
non-increasing (a lower ray hits terrain at or before a higher one), so
each row is one of three cases against the peak's distance D:

    |d − D| ≤ tol   → MATCH: label here (the rendered summit edge)
    d > D + tol     → farther terrain: the ray passes over the peak, keep going
    d < D − tol     → nearer terrain: everything below is nearer still → HIDDEN

The occlusion decision is the third line. It is correct — but its threshold
is `D − tol`, the same `tol` as the match, so **the tolerance is not a
sensitivity knob on the match; it is the width of the depth window in
which occluded terrain still counts as the peak.** (Since 2026-08-16 the
scan carries a second, tight window and returns a class — "The label
model" below; everything in this subsection is about the wide window,
which is unchanged.) Own-column verdicts on the 8 459 candidates:

| verdict | ±6% | ±25% |
|---|---|---|
| match | 667 | 1 716 |
| bracket (profile jumps from > D+tol to < D−tol: a ridge in front) | 363 | 99 |
| beyond (skyline itself nearer than D−tol: peak below the horizon line) | 7 429 | 6 644 |

±25% admits **1 049** features ±6% rejects: 785 of them are *behind the
skyline* in their own column, 264 are bracketed by a depth jump whose gap
is median 16–19% of D — ridges, not quantisation. (Last night's "667 vs
667" table re-anchored the 667 baked labels at ±25%; it measured where
they pin, not what the pool admits. Both are true; this one matters.)

**Angular second opinion.** The depth margin can't tell "hidden by a hair"
from "hidden by a mountain", so each rejection was re-checked from the
peak's own `ele` (eye 329 m, k = 0.13): θ_peak vs the skyline angle in its
column. Of the 7 429 "beyond": 98.2% sit more than 2 rows (0.05°) below
the ridge; 72 are marginal (|Δ| ≤ 1 row); **7** have an `ele` that says
they should poke over (Klíč, Strážný vrch, Zlatý vrch, Javor …, all
Δ +1.1–1.9 rows) — DSM canopy or OSM/DEM disagreement, the honest
"maybe". Of the 363 bracketed: none. So **±6% own-column is essentially
the correct visibility test at this render's resolution.** Loosening it
finds hidden features, not missed ones.

**Why ±25% nevertheless *looks* better**: what it adds first, in priority
order, is Liberec (81 km, behind a ridge at 74), Ústí nad Labem (66 km,
Elbe valley, ridge at 56), Teplice, Děčín, Česká Lípa, Kralupy — famous
places that are geographically in valleys and basins and genuinely not
visible from Ďáblice. On a 1600 px screen ±25% swaps 15 of the 27 displayed
names for those. The azimuth stays exact, the labels line up on the horizon:
a vista board. That is a legitimate reading ("this named place lies in
that direction") but it is not a visibility claim, and the graduated
overlay publishes labels to visitors as "this is what you see". If it is
wanted, it is a **separate label class** (e.g. `visible: false`, drawn
distinctly), never a cranked tolerance.

**What ±6% does miss — a spatial, not depth, error.** A ±1-column
neighbourhood search at ±6% recovers 22 features (13 beyond, 9 bracket);
±2 columns ≈ 40. These are summits whose OSM node sits one column (26–35 m
at 60–80 km) off the DEM summit or on the edge of a ridge dip — Strážný
vrch is both in this list and in the seven the `ele` check flags, which
cross-validates it. A small azimuth neighbourhood (±1–2 columns, or ±50 m,
whichever is wider) is the honest widening; the match tolerance itself
should stay where it is (matched |d − D|/D: median 2.2%, p90 5.4% — 6%
is the right size for 0.025° rows plus node wobble).

**Adjacent-row depth steps** on continuous terrain are median 0.5–1.5%,
p75 1–6% (grazing plains at 40–60 km reach 5–7%) — which is what the 6%
absorbs. Finer elevation rows in the render (0.025° here; the 4000-row
cap is far off) would shrink both the bracket ambiguity and the needed
tolerance; that is a renderer knob, separate from the label code.

### Percent or metres? — measured, then both

Residuals `|d_row − D|` of the 667 real matches grow with distance in km
(median 0.22 km at 5 km → 2.37 km at 90 km) but the *near-field* residual is
4.4 % — 220 m at 5 km — which is not sampling, it is the OSM node versus the
rendered summit edge: an absolute, summit-sized error. The renderer's own
depth precision IS relative (`renderer.py:264`: the march steps 0.005·d,
"constant RELATIVE depth error out far"). So the window is affine, and the
coefficients mean two things: **absolute = summit/node scale (~300 m),
relative = the march (~3 %)** for "this pixel is the summit"; and the wider
8 m + 6 % for "terrain at about its distance". Beyond ~40 km a 3–5 km
residual is a shoulder of the same massif (Smědavská hora seen at 91.7 km,
node at 95.7): the honest thing is to say *mass*, not to pick a coefficient
that decides it either way.

### The label model (built 2026-08-16)

Every label now carries a **class** derived from **evidence**, and the
evidence travels with it so any GUI can reveal how much a label claims
(`shared/terrain/peakLabels.ts` ⇄ `enrich/api/app/overlay_export.py`,
mirrored by hand; constants documented at `PEAK_DEPTH_REL_TOL`):

| class | evidence | text | painted |
|---|---|---|---|
| **summit** | tight window `300 m + 3 %·D` ∧ height band `100 m + ½ row` (POI's own elevation angle vs the anchor row, in METRES — the 30 m DEM renders sharp cones 60–85 m low, DSM canopy renders forested tops ~25 m high) | name + elevation (OSM only; a DEM-filled `ele` is not the summit's) | full |
| **mass** | wide window `8 m + 6 %·D` ∧ the same height band (measured 2026-08-16 evening: without the band the median mass label sat on terrain **139 m higher** than the named hill — a different landform; Jelení vrch, 324 m, 2 km in front of Malý Bezděz, was labelling Malý Bezděz's flank and, ranking nearer-first, thinning the real summit out) | name | full |
| **direction** | a **settlement** hidden in the own column and its ±1–3 neighbours (±50 m), priority ≥ 240 (a town of 5 000), ≤ 100 km, occluder ≥ 1 km away — peaks are never direction material: a hidden summit is simply not in the picture | name | dim, dashed leader that stops 8 px above the ridge line (the anchor is what hides the place; the line must not touch it), no anchor dot |

Settlements are binary — *seen* (tight ∧ height: the DSM renders their
roofs) or direction material; a hit at a town's distance but a different
height is the hill behind the town (Litoměřice +2.6 km/−7 rows, Litvínov
+4.3 km/−10 rows both moved from "labelled" to *direction*). Per label:
`class`, `seen_m` (depth at the anchor), `dh_m` (metres by which the POI's
elevation angle sits above the anchor row; + = ele says higher), `col_offset`
(azimuth-neighbourhood column used), `ele_estimated`. `labelText()` and
`labelEvidence()` render these; the pane's picked chip, the bench's status
line and the zoom view's tap-on-a-pill box all show the evidence sentence.

Also built: **one label per depth pixel** (visible classes first, then
priority) and the **azimuth neighbourhood**; direction labels are sorted
after every visible one so a first-come layouter never lets a hidden town
displace a visible summit. The pane's slider is capped at 0.10 and relabelled
"window" (it drives the wide window's relative term). Painting is shared:
`shared/terrain/labelPills.ts` for bench + zoom view, `dim` on
`LabelDrawCmd` for the pane's painter.

On 252a7ea8: **557 labels = 482 summit / 59 mass / 16 direction** (was 667
undifferentiated, then 658 before the height band applied to mass); 39
columns had carried more than one label per pixel; Emporturm is *hidden*
(`dh_m` −218: the pixel is the plateau rim 218 m above the tower, which
stands behind it — a different landform, not its mass); Milešovka, Ještěd,
Říp, Sedlo, Bezděz, Malý Bezděz *summit*; Strážný vrch *summit* via the +2
column; Smědavská hora *mass* (dh +23, seen 4 km in front). Sort order among
equal priority: summit before mass, then nearest.

### Explaining the pool (built 2026-08-16)

`explainPeak` / `explainPeaks` (peakLabels.ts) give EVERY candidate a
verdict and a one-sentence reason — the three label classes plus `hidden`,
`not-notable` (hidden and under the direction threshold), `too-close`,
`out-of-range` (render range or the kind's cap), `outside-sweep`,
`no-terrain` — and `projectPeak` is now just their labelled subset. The
terrain pane's **pool** panel lists the whole candidate set that way
(labelled first in emission order, pixel-losers marked, then the rest by
priority), with a name filter, per-verdict counts, and a "now" column
telling whether a label's slat is on screen at this zoom, thinned by a
neighbour, or beyond the fog; clicking a row centres the view on it. It is
the answer to "why does this POI make it and that one not" — e.g. Malý
Bezděz is a summit label that is merely thinned at overview zoom (0.5°
from Bezděz, no prominence tag so placed after it), and Bělá pod Bezdězem
misses the direction threshold by two priority points.

Fog on the pane is now also the label cutoff (it was only the GL haze
uniform, while the bench's fog is the model's `visibility_km` — same word,
two meanings; the pane's labels beyond the visibility distance now drop
out with the haze).

### Where the tolerance is set

* Terrain **pane** (`/terrain`, TerrainViewer): slider 0.01–0.10, default
  0.06, UI state only — the WIDE window's relative term (the `?` next to it
  explains). Above ~0.10 it was a different question, now answered by the
  direction class. The TIGHT window's 3 % and the height band are constants
  everywhere; both windows are always in effect: wide decides *whether* a
  POI is labelled, tight ∧ height decides whether it is a *summit*.
* Overlay **bench** and **export**: the constants above, no slider.
* Visibility cutoff (`visibility_km`) is the one editorial tolerance-like
  setting and lives in the fit.

### Density and sorting

* **Display density — slats (built 2026-08-16).** `layoutSkyLabels` now
  lays each label as a slat rising from just above its summit at
  `angleDeg` (default 45°, `SKY_LABEL_ANGLE_DEG`): parallel slats tile like
  the slats of a blind and never collide however long the names are, so
  the only constraint is anchor spacing Δx·sin θ ≥ pillH + gap, there is no
  stacking, and left-to-right reading order is azimuth order (the vista
  board property). One same-orientation-rectangle overlap test covers every
  angle; 0° is a horizontal *non-stacking* layout. Measured on the
  graduated Ďáblice document at 1600 / 3200 / 6400 px: horizontal +
  stacking (the old layouter) 27 / 56 / 97; **45° slats 36 / 72 / 130
  (+33 %)**; 60° slats 43 / 87 / 154 (+59 %); 0° non-stacking 9 / 25 / 54.
  Less than the 2× the geometry allows, because real anchors cluster and
  sit at different heights. `hitSkyLabel` inverse-rotates the tap; one
  painter (`shared/terrain/labelPills.ts`) now serves the pane, the bench
  and the zoom view — the pane no longer uses the zoomview annotation
  painter, and `minGapX` is an optional extra floor (default 0).
* The pane hands only the first 150 marks to the layouter; bench and zoom
  view hand all — same render, different names at the same zoom. Not yet
  reconciled.
* **Sorting is the weak spot.** Prominence covers 288 of 41 461 pool
  features (1.4 %); among the rest, nearest-first is arbitrary (a landfill
  tagged `natural=peak` at 1.7 km outranks Radobýl). Measured alternatives:
  `ele` desc → the top 30 are all Jizerské hory tops (bad); **skyline
  salience** (label row − median skyline over ±0.5°) → Milešovka / Sedlo /
  Bezděz +4 rows, the tower cluster +0.5, but Říp and Ještěd 0 (Říp is wider
  than the window at 30 km; Ještěd sits on a high ridge) — window-dependent,
  usable as a bonus, not a rank. Better signals live outside the depth
  buffer: computed prominence / relief from the DEM at pool-build time, or
  OSM `wikidata` presence (Overpass returns it; `/terrain/peaks` drops it).
* **Distance-gate untagged peaks** — a 62 m bump at 80 km is not a landmark;
  `PLACE_MAX_DIST_M` is the precedent.

### Horizontal shift per segment (built 2026-08-16 evening)

The fit gained `hwarp?: number[]` — an azimuth SHIFT in degrees per
segment, on the same knots as `warp`: `hwarp[k]` moves the whole panel
that starts at handle k (the last entry has no panel). Piecewise
CONSTANT, deliberately not interpolated: a stitching seam is a step and a
mis-stitched panel is shifted whole, not stretched — a vertical warp alone
could lift the curve onto the ridge at a handle while the peaks left and
right of it stayed displaced sideways. Projector: `unproject` adds the
segment's shift to the ideal azimuth; `project` finds the first segment
(left→right) in which x = xIdeal(delta − shift_k) actually falls — an
azimuth in a seam GAP does not project (the pano really does not show it),
one in an overlap shows once. Round-trips to 1e-6° in all three
projections. Bench: dragging a handle sideways shifts its panel AND every
panel to its right (a stitched pano's error accumulates seam by seam);
Alt-drag = this panel only, Shift-drag = vertical only; handles are drawn
where their panel's content now sits; the segment count is a number input
(1–48, `+`/`−`), `level` zeroes both arrays. Serialised ONLY when non-zero
(bench payload and `_overlay_fit_json`), so every fit saved before the
field existed keeps its canonical JSON and stays "landed". Hillview stores
the fit verbatim and the zoom view's projector applies it — no backend
change.

### Save / revert / undo (built 2026-08-16 evening)

The bench keeps the last SAVED fit in memory and shows the state
explicitly — `never saved` / `unsaved changes` / `saved ✓` — with
**revert** (back to the saved fit; drops the server draft and this tab's
live key; undoable), **undo/redo** (↶ ↷, Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y;
one entry per settled change — a drag's stream of moves or a slider's run
coalesces 500 ms after the last), and `save fit` enabled only when there
is something to save. On load it says plainly when the restored draft
differs from the save ("restored draft — unsaved changes since the last
save (revert to drop them)"). The auto-draft keeps running underneath — it
is what lets two windows share the working state — but it is no longer
the only state you can see, and a stray drag is one Ctrl+Z away.

## Open questions

- **Thresholds on a second render** — 300 m / 3 % / 100 m / ±50 m / 240 /
  100 km were set on one Ďáblice render; a Prosek or Krkonoše render may
  move them. The evidence fields make that a query, not a re-bake.
- Reconciling the pane's 150-cap with bench/zoom view (which hand every label to the layouter); whether 60° should be the default (reads a little worse, +60 % vs +33 %).
- **Ranking signal for the untagged 98.6%**: DEM relief at pool time vs
  wikidata presence vs skyline salience — its own small project.
- **Row resolution**: whether photo-wedge renders should use a finer
  elevation step than the azimuth step.
- Payload size is explicitly NOT a concern (tens of KB); do not trade
  correctness for it.
- Whether `user_adjust` ever flows back into the bench as a draft
  (mechanism exists via the mirror; product call deferred).
- Whether the depth blob should live in the photo pyramid pool or a
  dedicated terrain pool — currently the write pool, under `terrain/`.
- The zoom view probes `GET /photos/{id}/terrain-overlay` on every photo
  open so the display menu knows whether to offer the toggle; for a photo
  that has an overlay that is ~166 KB nobody asked for. A summary mode, or
  a `has_terrain_overlay` flag in the photo feed, would fix it — API-shape
  decision, deferred.
