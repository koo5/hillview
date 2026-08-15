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

Measured on the same render — 667 labels over a 93.8° / 106 km view:

* **Occlusion is sound at the default ±6%.** Of the 242 labels anchored
  below the skyline, *all 242* are genuinely nearer than the ridge at their
  column — real foreground hills in front of a distant horizon. Zero
  occluded summits slipped through.
* **What enforces that is the monotonicity stop, not the tolerance.** Below
  the skyline a column's depth is non-increasing (a lower ray hits terrain
  at or before a higher one), so `if d < distance - tol: break` means "we
  have met terrain nearer than the peak; everything below is nearer still;
  the peak is hidden". It fires before a loose tolerance can rescue an
  occluded peak.
* **But the stop's threshold IS `distance - tol`, so widening the tolerance
  disables it.** At the pane slider's max (±25%):

  | | ±6% | ±25% |
  |---|---|---|
  | pinned to the first terrain row (never occlusion-tested) | 57% | 75% |
  | anchored to terrain >5% off the peak's own distance | 104 | 269 |
  | worst anchoring error | 6% | 25% (15 km) |

  Slánský kopec (38.2 km) lands on terrain at 47.7 km; Litoměřice, a town
  in the Elbe valley at 50.1 km, is pinned to a skyline 10 km behind it.
  301 features appear at ±25% that ±1% rejects.

  **This is a semantic slide, not a sensitivity knob.** ±1% answers "this
  summit is the thing you see there"; ±25% approximates "this named place
  lies in that direction" — a vista-board reading, which is legitimate and
  looks tidier (azimuth stays exact, labels line up along the horizon) but
  is no longer a visibility claim. The graduated overlay publishes it to
  visitors as fact, so the two should be separate modes rather than ends of
  one slider.
* **Resolution crowding is real.** 71 grid columns carry more than one
  labelled peak (157 peaks total). Column 2989 (az 13.24°) holds **ten**
  Elbe Sandstone climbing towers at 79–81 km — Emporturm, Falkenturm,
  Oertelwand, … — none with a prominence tag, so the priority sort falls
  through to nearest-first and picks one arbitrarily. Their centres span
  0.023°, *less than one render column*; each spire is itself wider than
  that spacing (a 40 m tower at 80.6 km subtends 0.028°), so they overlap
  into one silhouette. On this photo (830 px/°) the whole cluster is 19 px
  against a 21-px render column; at a hypothetical 200 000 px / 90° it
  would be ~51 px of centres inside a 56-px column. The render is not
  meaningfully under-resolving — the ten OSM points are sub-feature detail
  on one massif.
* **The pool is mostly minor features**: only 10% carry a prominence tag,
  and among those the median prominence is 62 m.
* **Inconsistency to resolve**: the tolerance slider lives on the terrain
  *pane* and viewer. The overlay fitting bench calls `projectPeaks` with no
  tolerance argument and the export hardcodes the same default — both are
  pinned at 6%. So the setting a curator tunes is not the setting that
  graduates.

## Open questions

- **Tolerance semantics** (the live one): keep graduation at ±6% as a
  visibility claim, and if the vista-board reading is wanted, add it as an
  explicit azimuth-only mode rather than a cranked tolerance. Needs bench
  time to decide what "better" means.
- **Capture the tolerance in the fit** so the export reproduces what the
  curator approved, instead of both sides silently defaulting.
- **Per-column label cap** — keep the highest-priority label per grid
  column. If the render cannot separate them, emitting ten labels claims a
  resolution that does not exist. (~86 labels here; a legibility and
  honesty fix, not a size one.)
- **Distance-gate unprominent peaks** — a 62 m bump at 80 km is not a
  landmark; `PLACE_MAX_DIST_M` is the existing precedent for settlements.
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
