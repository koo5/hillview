# Vision / Enrichment Subsystem — Design

Status: **planning / greenlit**, no implementation yet · Last updated: 2026-06-13

Algorithm-assisted **identification and geolocation of features in photos** — the distant
buildings, hills, towers, churches and landmarks visible in panoramas and wide shots — to
replace the by-hand annotation workflow.

## How this doc is organised (read this first)

It's built to grow without constant rewrites:

- **Part I — Context** (§1–§4): stable. Motivation, settled decisions, the data/signals we
  have, the system architecture. Changes rarely.
- **Part II — Technique catalogue** (§5): *additive*. Each entry is one modular way to pin down
  a piece of information ("locate this", "name that", "fix this bearing"). **Found a new method?
  Add a card. Don't rewrite anything else.** Each card notes its maturity: 💡 idea · 🔍 grounded
  in code · ✅ verified on data.
- **Part III — Composition** (§6): the *evolving* part. How we'd currently chain the catalogue
  into useful flows. This is expected to change often; it references cards by `id`, so editing
  strategy doesn't disturb the catalogue.
- **Milestones / risks / appendices** (§7–§9, A–B): first experiments and the grounding evidence.

---

# Part I — Context

## 1. Motivation

Today, annotation rectangles on panoramas are drawn **by hand**: track down close-up photos,
scour maps to identify distant features, box and label them. We want algorithms to assist:
auto-derive feature metadata on ingest, and — when a rectangle is drawn in zoomview — propose
*what* it is and *where* it is, as candidate annotations to approve or edit. This is a new big
subproject; its sibling in the backlog (full 3D earth reconstruction) shares the same machinery
(see §5 `sfm-bundle`, §10).

## 2. Background & decisions (greenlight context)

- **Separate enrichment database** (PostGIS + pgvector), not new tables in the main DB. It
  mirrors the photos it needs; the main Hillview Postgres stays source of truth.
- **Localization is primarily a matching+triangulation problem, not a ray-cast problem.** Phone
  bearing is too biased to identify a distant POI by casting a single ray (see §3). Feature
  correspondences across photos — which need no reliable absolute bearing — are the engine;
  ray-cast demotes to a *candidate gate*. (This reversed an earlier "geometry-first" framing.)
- **Manual effort should reduce to approving a match in a few clicks**, not measuring bearings.
- **Pose/bearing/projection are noisy priors to refine, never ground truth.**
- **The matching/geometry backend is pluggable** (§5 `feature-match`, `sfm-bundle`): a thin
  classical baseline on CPU now; a DUSt3R/VGGT-family model later (§10).
- **Success metric:** reproduce the existing **457 hand-drawn, hand-labeled rectangles across 42
  photos** (the gold set, §3). Anchor specimen: `c953f7df` (App. B).
- **External map data:** OpenStreetMap (primary) + Copernicus GLO-30 DEM (supporting), §3.

## 3. Data & signals we have (what techniques draw on)

Live snapshot (~28 k photos, 2026-06-13):

| Signal | Reality | Use / caveat |
| --- | --- | --- |
| Camera position (`geometry`) | **99%** present | GPS error (metres–tens of m) |
| Bearing (`compass_angle`) | present on **all non-deleted** (cornerstone of the DB) | **biased & unreliable** as a *measurement* — per-session/device offset + heading-dependent distortion (*the central problem*) — but its guaranteed presence makes it a universal **pairing/gating key** despite the bias (e.g. bearing-gated pair selection with a generous window, `raycast-gate`, view-pie candidate gates) |
| Altitude | 19% | sparse → read from DEM at the point |
| Focal length (`FocalLength35efl`) | 15% (Canon) | FOV for a minority; panos carry per-frame `v` in the `.pto` |
| Big images (DZI) | 20,288 | deep-zoom pyramids exist |
| Panoramas (aspect ≥2:1) | ~50 | high-value subset; projection **varies** (App. B) |
| `analysis` (LLM) | 93% | features list, `closest/farthest_object_distance` (m), `visibility_distance`, etc. — strong priors |
| Annotations | 457 current on 42 photos | RECTANGLE + normalized/pixel coords; bodies are **named landmarks** (towers, churches, towns), many `?`; some carry coords/URLs |

**External:** OpenStreetMap (towers/churches/masts/water-towers/named places/peaks — excellent
Czech coverage) as the **primary** name source; **Copernicus GLO-30 DEM** as supporting
(occlusion, horizon-fit heading, altitude, bare hills). All gold photos cluster around
Prague/Bohemia.

**Upstream (`pics`):** RAW CR2s + per-frame `.CR2.geo.xmp` (lat/lon/bearing) + GPS-log/correction
CSVs, and for panos the stitch `.pto` (per-frame pose, projection, FOV) + `pano_trafo`. See App. B.

## 4. Architecture (stable)

```
Hillview Postgres (photos, annotations) ── source of truth
        │ read-only poll (skip_locked, like scripts/analyzer)
        ▼
 enrich-sync ──► EnrichDB (separate: PostGIS + pgvector)
                   photo_mirror · pose(+uncertainty,provenance) · embedding · keypoints/desc
                   · geometry_artifact(depth/pointmaps) · poi(location,source,confidence) · match
        ▲                                    ▲
  pics-side enrich jobs (.pto/RAW/pano_trafo) │  Hillview-side pollers (analyzer-cloned)
        └──────────────── compose (§6) ───────┘
                          │
   Hillview backend: POST /api/match/suggest  ◄── zoomview rectangle-draw → approve-in-a-few-clicks
```

- **Pollers** clone the analyzer skeleton: poll-for-null + `skip_locked`, content-addressed file
  cache of expensive ops, write back. Heavy/RAW/`.pto` work runs **pics-side**; latency-sensitive
  query runs **Hillview-side**.
- **Pluggable geometry backend** behind one interface (images → matches + pose + optional depth):
  classical (RootSIFT/LightGlue + BA) now, DUSt3R/VGGT later (§10).
- **Annotation gains a structured `location`**: `{lat, lon, source: manual_map | triangulated |
  proximity | osm_matched, confidence}` — serves as anchor, output, and training signal.
- **Online path:** `createAnnotation` (zoomview) → `POST /api/match/suggest` → render candidate
  matches as read-only overlays (reuse the existing detection-overlay pattern) → approve → write.
- **Outputs:** experiments emit **self-contained HTML reports** (open in a browser) — crops,
  candidate matches, maps, residual plots — not just console logs.
- **Product surface (north star):** selecting/creating an annotation opens a **matches
  sidebar/popup** — candidate photos + a map + one-click *accept → locate & label*. The same
  `map-pick` panel (pan a map to the POI, save) is the manual anchor path.
- **Deps & data conventions:** Python via `uv`, pinned for reproducibility —
  `uv tool install --exclude-newer "$(date -d '6 weeks ago' +%F)" …`. Data source is the
  `photos.csv`/`photo_annotations.csv` export (now `~/hggg`; a fresh prod dump is incoming); every
  script takes `--data`. No local Nominatim (see `geocode-fwd`/`osm-reverse`).

---

# Part II — Technique catalogue (additive — add a card, don't rewrite)

Maturity: 💡 idea · 🔍 grounded in code · ✅ verified on data.

### 5a. Identify *what* it is

| `id` | Produces | Needs | Maturity | Notes |
| --- | --- | --- | --- | --- |
| `llm-analyze` | per-photo features, rough distances, description | image | ✅ running | the existing `scripts/analyzer`; strong prior for gating |
| `osm-reverse` | nearby named OSM features (tower/church/peak/place) | a **location** + OSM | 🔍 | the existing `backfill_places.py` `/reverse` pattern (stores `geocode`/`place_name`/`place_slug`); self-host Nominatim/Photon for bulk |
| `geocode-fwd` | coords for a named place/POI | label text + a geocoder | 💡 | forward `/search` (Nominatim/Photon); public OSM OK for *small* calibration runs only; many bodies already carry coords |
| `llm-toponym` | resolved name/ref from free-text label | annotation text + a **local** OSM candidate set | 💡 | handles `Hl. n.`→Hlavní nádraží, CZ abbrevs, multilingual; easy once *location-gated* |

### 5b. Localize *where* it is (and recover pose)

| `id` | Produces | Needs | Maturity | Notes |
| --- | --- | --- | --- | --- |
| `raycast-gate` | rough half-plane → *candidate* photos/POIs | pose (noisy ok) + GPS + `llm-analyze` tags | 🔍 | **gate only**, not a reliable POI fix — this is all biased bearing is good for |
| `feature-match` | image↔image correspondences / relative pose | ≥2 images, pixels | 🔍 | **LightGlue** is the default (learned, CPU-OK, handles our scale gaps); RootSIFT = sanity baseline only; MASt3R/VGGT for the hardest pano↔close-up. Needs **no absolute bearing**. The SOTA models (§10) are *implementations of this card*, not an alternative pipeline |
| `proximity-transfer` | POI location ≈ a near photo's GPS | a single match to a photo shot *near* the POI + `closest_object_distance` | 💡 | **the primary localizer for distant POIs**: short ray ⇒ bearing-insensitive, needs only one good match |
| `triangulate` | POI location from ray intersection | bias-corrected correspondences from ≥2 **separated** views | 💡 | **numerically poor for distant POIs from nearby cameras** (long thin error ellipse) — reserve for widely-separated viewpoints (e.g. two panos km apart) |
| `pto-map` | pano rect → source frame + in-frame ray | canvas `.pto` + `pano_trafo` | ✅ verified | bypasses the bent-canvas problem; per-frame clean geometry (App. B) |
| `horizon-fit` | absolute heading | DEM + visible bare horizon | 💡 | good for terrain panos; weak in dense city |
| `anchor-ground` | a pano's absolute pose | a few **manual** map-measured POI bearings | 💡 | minimal-manual fallback; feature-match can automate the anchors |
| `sfm-bundle` | refined poses + sparse 3D + bias, jointly | many matches + GPS priors | 💡 | capstone; DUSt3R/VGGT backend; converges with 3D-reconstruction backlog |
| `dem-occlusion` | prune occluded candidates | DEM + a ray | 💡 | visibility test along the line of sight |

### 5c. Refine & calibrate

| `id` | Produces | Needs | Maturity | Notes |
| --- | --- | --- | --- | --- |
| `bias-calib` | corrected bearings across a whole session | ≥1 anchored photo (matched POI or `anchor-ground`) | 💡 | exploits the *systematic* per-session/device magnetometer bias → cheap DB-wide error drop |
| `geo-sidecar-fill` | per-frame lat/lon/bearing for pano frames | source-dir `.geo.xmp` (exists) or GPS log | 🔍 | join by CR2 stem, or generate in-bucket (App. B) |
| `map-pick` | a POI's exact coords (ground-truth anchor) | a human + a map UI | 💡 | click annotation → pan map to the POI → save → `location{source:manual_map}`; cheap, exact, the fallback when auto-match fails |
| `fit-calibration` | a pano's effective FOV + projection + bearing bias | ≥~5 geocoded anchors on the pano | 💡 | solve the angular model from the labels themselves → reduces dependence on collecting old `.pto`s; residual-vs-x reveals canvas-bend corruption |

---

# Part III — Composition (evolving — how we'd currently chain them)

The central UX everywhere: **propose → user approves in a few clicks → we commit a `location`.**

- **R1 · Locate one pano POI (the core loop).**
  `pto-map` (rect→frame ray) → `raycast-gate` + GPS-proximity + `llm-analyze` tags pick a handful
  of candidate photos → `feature-match` against them → **approve** → `proximity-transfer` (if a
  near photo matched) *or* `triangulate` (if ≥2 separated views) → `location` →
  `osm-reverse` + `llm-toponym` → label. Each confirmed match feeds `bias-calib`.

- **R2 · Locate a single clean frame (simplest first build).** Same as R1 without `pto-map`
  (the frame *is* the image, already perspective — no pano caveat). The ~7 gold single
  8688×5792 frames are the easiest targets. Concretely: crop the rect → `raycast-gate` (GPS +
  biased-bearing fan + `llm-analyze` tags) shortlists corpus photos → `feature-match`
  (**LightGlue**) → approve → **`proximity-transfer`** (primary) or `triangulate` (only if
  widely-separated views) → `location` → `osm-reverse` + `llm-toponym` → label. R2 is the
  *harness*; swapping LightGlue→MASt3R/VGGT is a one-card change.

- **R3 · Ground a whole panorama.** Accumulate anchors (manual `anchor-ground`, or approved
  `feature-match`es) → `sfm-bundle` → refined pano pose improves *every* ray from it; add
  `horizon-fit` where a bare skyline exists.

- **R4 · DB-wide bearing cleanup.** Any session with ≥1 anchor → `bias-calib` → propagate the
  correction to all its photos, annotated or not.

As techniques mature (💡→✅) and new ones appear, edit *this* section; the catalogue and context
stay put.

---

## 7. Workstreams, milestones & roadmap to 3D

Now several parallel lines of work — some blocked on data collection, some runnable today.

### Workstreams (parallel)

- **W1 · Data foundation.** Fresh **prod DB dump** (in flight); annotation **`location` field** +
  **`map-pick` UI** to materialize anchors; **`.pto`/RAW archaeology** — collect & organize the
  historical pics outputs across old pipeline versions (a sizeable effort of its own); geocoder
  setup (`geocode-fwd`/`osm-reverse`).
- **W2 · Geometry calibration.** `fit-calibration` + `bias-calib`: labels-as-anchors → per-pano
  FOV/projection/bias; quantify how usable the bearing is and how much the canvas bend corrupts the
  angular model. Output: trustworthy per-pano rays + a labeled anchor set.
- **W3 · Matching & localization.** `feature-match` (LightGlue→MASt3R) gate→match→
  `proximity-transfer`/`triangulate`; the approve loop. **Candidate gating = the view-pie**
  (position + bearing ±60° + range ≈ `farthest_object` × `slack`, same-side ±90°). Tuning it is its
  own small line: the range gate enforces *distance ≤ view-depth × slack* (a photo that can't reach
  the POI is dropped); `VIEW_SLACK` now 2 (was 5), missing-`far` default 2000 m (was a 25 km bug),
  and the inspector exposes it live via `?slack=N`. The matcher itself is a **pluggable backend** —
  MASt3R today; VGGT/MegaDepth-X next, each more robust to weather/daytime/season (the cross-time
  regime that gates walk-to-walk merging), so this improves for free as models ship.
- **W4 · Naming.** `geocode-fwd` + `llm-toponym` + `osm-reverse`.
- **W5 · Product UX.** `POST /api/match/suggest` + matches sidebar/popup + `map-pick` +
  accept-to-annotate.
- **W6 · Infra.** EnrichDB (PostGIS+pgvector), analyzer-cloned pollers, `oneoff` venv fix.
- **W7 · Reconstruction & world model (MASt3R-SfM).** The "model the world bit by bit" thrust —
  local reconstruction of dense clusters/walks, validated against GPS (contiguous walk **2.9 m**
  median residual; strided sampling drifts to **81 m** — don't subsample sweeps), `--mask_anon`
  removes blurred/dynamic objects (cars/people) via the worker's `blurred` flag. Scales up as
  **walk = submap → GPS-anchored pose-graph** with *verified* visual loop closures (the
  Doppelganger-rejection capability becomes load-bearing here) + DEM ground constraint, grown
  incrementally; Gaussian-splatting is the photoreal downstream; GPU for N²/retrieval pairing and
  splat training. Storage: keep poses+sparse (~16 MB/walk) canonical, regenerate dense/splats. This
  is the trustworthy backend that finally lets W3 reject the Doppelgangers pairwise matching can't.
  Full empirical log: [`reconstruction-field-notes.md`](reconstruction-field-notes.md).
- **W8 · Annotation format & geocode hygiene.** Stabilize the free-form annotation **body text** into
  a structured reference (e.g. `name · type · [wiki-url] · [coords]`) and formalize `oops`/`?` as
  real flags, not prose. This is the **upstream fix** for wrong geocodes: robust Theil-Sen
  calibration only tolerates a *minority* of bad anchors, so cleaner references → fewer wrong
  geocodes → stable per-pano calibration *and* better identification. Touches the app's annotation
  UI + a migration of existing bodies.

### Milestones (runnable order)

- **M1-0 — feasibility ✅ (done).** Corpus has abundant co-visible/near candidates for all 11 clean
  targets (`scripts/enrich/r2_select_and_gate.py`).
- **M1-1 — anchor resolution + pano calibration ✅ (done 2026-06-15).** Over all 19 panos:
  `resolve_anchors.py` (body-coords → Wikipedia coords → unbounded geocode + bearing/distance
  post-filter; `oops` skipped) → **261/461 located, 230 clean, 31 flagged**. `calibrate_panos.py`
  robust **Theil–Sen** fit of geocoded-azimuth vs rectangle-x per pano → **bias is per-pano**
  (median +0.4°, robust spread **±14°** — *not* a global declination; one pano −31°), inlier
  **RMS 1–2°**, and **FOV recovered from labels** in the right ballpark (`333e8851` 80°; `f4b4d58c`
  138° vs its known `.pto` **122°** — labels pin FOV to ~10–15%, the `.pto` crop/projection tightens
  it). Geocode-error detection, layered & non-circular: gates 31 + consensus residuals ~42 +
  cross-pano 2. Reports: `annotation_anchors.html`, `pano_calibration.html`, `geocode_debug.html`.
  Caveat: linear (equirect) fit — rectilinear panos (`333e8851`) want their `.pto` projection. Note:
  fresh prod dump uses **WKT** geometry (old export was EWKB hex); parsers handle both.
- **M1-2 — matching.** `r2_match.py`: LightGlue on a target's near-candidates → correspondences →
  `proximity-transfer` → location → HTML report.
- **M-recon — MASt3R-SfM "reconstruct a bit of the world" ✅ demo ready (2026-06-16).**
  `scripts/enrich/reconstruct.py` drives the full MASt3R-SfM (`sparse_global_alignment`: forward
  pass → matching → 3D optim → 2D refine → triangulation) on a dense local cluster, end-to-end on
  **CPU**. Selects a capture-time-contiguous slice of close-range photos from the dump (Prosek
  cluster, 312 photos / 300 m), downloads, reconstructs, exports `scene.npz` + `points.ply` +
  `report.html`. **Validation = the recovered camera track, aligned to GPS by a Umeyama similarity
  only, vs GPS itself.** First run (5-photo 71 s burst): ~30 k sparse points, **median camera↔GPS
  residual 5.2 m** (mean 4.9, max 7.5) — i.e. *within phone-GPS noise*. MASt3R estimates focal from
  pixels alone at ~395 px/512 ≈ 52–65° FOV (correct phone lens), 5 frames within 4%. This is the
  reconstruction-driven path: **global consistency is what pairwise matching can't give** — a
  Doppelganger that fools one pair cannot register into a coherent multi-view solve. Compute note:
  **512 is MASt3R's native resolution** (not a downgrade), so a GPU buys *speed, not detail* — ~32
  s/pair CPU → sub-second GPU (30–100×), turning N² whole-cluster reconstruction from weeks into
  hours. Forward passes cache per-machine. Result: **strided sampling fails** (`walk_sparse`, every
  ~8th frame → 81 m drift, cameras collapse) while **contiguous holds** (`walk_dense` → 2.9 m) — but
  *only at the drift-gate level*: on eyeballing, the contiguous walk didn't actually solve well, so
  the GPS residual is a **drift gate, not a quality score** (need MASt3R's 2-D reprojection error
  instead). Selector now filters `deleted`, selects by **capture-time window** (list-index selection
  silently mixed months), and supports `--pairs swin|complete|bearing`, `--inject` (Doppelganger
  test), `--mask_solocator` (image-fixed overlay), and a three.js cloud viewer on :8765. Board test
  so far **inconclusive** (printed-panorama content fools depth). Headline next: the **Prosek Rocks
  vantage** GPS-cluster + the **walk→world** merge (stage 5 above). Full empirical log in
  `docs/reconstruction-field-notes.md`.
- **M2 — naming + DB-wide `bias-calib`. M3 — product UX. M4 — DUSt3R/VGGT backend + corpus scale.**

### Roadmap: from annotations to 3D

One throughline; each stage reuses the last and stands alone in value.

1. **Anchors & calibration** (W1+W2) → trustworthy per-pano poses + a ground-truth anchor set.
2. **Assisted localization** (W3+W4+W5) → *draw a rectangle → see matches → one-click locate &
   label*: the day-to-day workflow.
3. **Joint pose solve / SfM-lite** (`sfm-bundle`) → bundle-adjust overlapping photos & panos with
   anchors + matches + GPS priors → globally consistent poses + bearing bias **+ sparse 3D points
   (the landmarks themselves)**. Where the MASt3R/VGGT backend earns its place.
4. **Dense 3D** → extend the sparse solve to dense depth/point maps (VGGT/MASt3R/MVS), fuse across
   the corpus → a 3D model of the photographed areas. This *is* the backlog's "3D earth
   reconstruction," reached by scaling the same machinery — and our corpus is exactly MegaDepth-X's
   target regime (sparse, noisy, in-the-wild).
5. **Walk → world (global merge)** → reconstruct **per-walk submaps** (locally rigid, GPS-anchored,
   metric), then a **pose graph over submaps** — nodes = walks, edges = relative transforms from GPS
   priors + *verified* visual overlaps — optimized to distribute drift, grown incrementally. The hard
   sub-problem is **trustworthy inter-walk loop closure**: a single false link (lookalike places, the
   board) warps the whole model, so loop closures must pass the reconstruction-consistency check —
   the anti-Doppelganger thesis, now global. GPS is the *gauge* (frame + drift bound + metric scale),
   visual matching is the *glue* (snaps metre-scale GPS seams), DEM is a coarse vertical/scale sanity
   constraint. Optionally each submap → a **Gaussian splat** (separate GPU optimization *seeded by*
   these poses + sparse points). Field log: `docs/reconstruction-field-notes.md`.

So 3D isn't a separate project; it's the terminus of the localization pipeline once matching +
joint pose-solve mature and scale.

**Methodology caveat (learned 2026-06-16):** the cheap validation metric — recovered camera centres
vs GPS after a 7-DoF fit — is only a **drift gate**, not a quality score (it catches the 81 m strided
collapse but rates a visually-poor walk at 2.9 m). Trust **structure-level** signals (MASt3R-SfM's
own 2-D reprojection error; eyeballing the cloud/depthmaps), not the GPS residual, before calling a
reconstruction good. And on **masking** inputs, **don't paint (gray/black fill)** — a fill adds a
boundary the corner detector grabs, and a detector-free dense model (MASt3R) doesn't ignore the flat
fill either. Use **crop** for fixed edge bands (the Solocator top bar) and **correspondence-level
masking** otherwise — drop matches whose endpoint lands in a per-image mask, never touch pixels (cf.
DynaSLAM, MASt3R `mask_sky`). Validated: it drops the image-fixed Solocator green-overlay false
matches (152/1226 on a test pair). Remove clutter *pinned to the image* (overlays — guaranteed
false-match hazard); the worker's random *scene-pinned* anonymization doodles are low-stakes (same
correspondence-mask tool when needed). Details: `docs/reconstruction-field-notes.md`.

## 8. Risks

- **Bearing bias** is the central data risk — mitigated by `feature-match` (bearing-free),
  `bias-calib`, and `anchor-ground`; *not* by trusting `raycast-gate`.
- **Pano↔close-up scale gap** is the hard case for any matcher — mitigated by the geometric
  candidate gate proposing only plausible pairs, and by `proximity-transfer` needing only a coarse
  match.
- **No lossless originals / 8192 px `full` ceiling** (App. A) — fine for prototyping; the 142 k-px
  panos need DZI tiles or the upstream source frames for full detail.
- **Pitch/roll never logged**, **per-frame geo not in pano buckets** (App. B), **pgvector not in
  the stock image**, **cross-DB sync** — all small known work (App. A).

## 9. Reference implementations in the codebase

- **`scripts/analyzer/`** — the poller template (poll + `skip_locked`, content-addressed cache,
  distill, write-back) and the `Photo.analysis` priors.
- **`pics`** (`~/repos/koo5/pics/0/pics`) — RAW→pano factory; Luigi DAG; `src/lib/gps_log.py`
  (`Location`/`OrientationRecord`); `src/pano/pano_pipeline.py` (+ `pano_trafo`); `oneoff/` runner.
- **`backend/api/app/cache_service.py`** — PostGIS patterns (GIST, `ST_Within`, grid sampling).
- **`frontend/.../OpenSeadragonViewer.svelte`** (`createAnnotation`, detection overlays) +
  `annotationApi.ts` — the zoomview hook and overlay-rendering pattern.

## 10. State of the art (the pluggable backend for `feature-match` / `sfm-bundle`)

The classical detect→match→RANSAC→BA→MVS pipeline is being replaced by feed-forward 3D models:

- **VGGT** (Oxford VGG + Meta, CVPR 2025 best paper): 1→hundreds of **unposed** images → camera
  params + depth + point maps + tracks in <1 s. Perspective-only. <https://vgg-t.github.io/>
- **MegaDepth-X** (Snavely/Cornell, CVPR 2026): dataset (1865 reconstructions) + finetuned models
  for *sparse, noisy internet collections* — nearly a description of our corpus. Built on
  MASt3R-SfM. <https://megadepth-x.github.io/>

Lineage DUSt3R→MASt3R→VGGT. They slot behind `feature-match`/`sfm-bundle` as the M4 swap. Caveats:
perspective-only (panos need reprojection to tangent crops — `pto-map`/source frames already give
this), and they output *relative/metric* geometry, not earth coords or names — so `osm-reverse` +
`llm-toponym` + GPS anchoring remain the georeferencing layer. Schema anticipates their dense
artifacts (`geometry_artifact`).

---

## Appendix A — Reality check (verified against code, 2026-06-13)

| Assumption | Verdict | Evidence |
| --- | --- | --- |
| Sibling service can poll the DB like the analyzer | HOLDS | `SessionLocal` reused; Postgres on a host port |
| Separate EnrichDB container can connect | HOLDS | new container reaches `postgres:5432` |
| Zoomview suggest-on-draw hook | HOLDS | `OpenSeadragonViewer.svelte:925` `createAnnotation`; overlay pattern `:356–373` |
| Image pixels good enough for matching | WORKABLE | `full` = q97 WebP, native ≤8192 px (`photo_processor.py:35,533`); **no lossless original**, >8192 px only as lossy DZI tiles |
| pgvector available | WORKABLE | `postgis/postgis:15-3.5` has PostGIS, not pgvector → build a combined image |
| `oneoff` runner reusable | WORKABLE | byte-identical to pics; needs `venv_py` path `src/pipeline`→`backend` |
| Bearing usable as a *fix* | **NO** | biased; usable only as `raycast-gate` (see §3) |

**Other gaps:** upstream pose/projection never crosses to Hillview (`upload.py:402–449` sends only
lat/lon/bearing/encoding) → compute pano targets pics-side, ship answers; pitch/roll captured for UI
only, never logged; no `is_pano`/projection field on user photos (aspect-ratio inference).

## Appendix B — Pano rect → source-frame mapping (verified: code + workdir `/shared/autocopy/2026-06-08-grebovka`, 2026-06-13)

The `pto-map` technique. For bent/straightened panos we never de-warp the canvas — we map the
rect to its **source frame** and use that frame's clean geometry.

- **Projection VARIES per pano — read the `p`-line `f`, never assume.** Grebovka: `pano1` = `f0`
  (rectilinear), the other five = `f2` (equirectangular); panoramic FOV `v` 26°–260°. `pano_trafo`
  reads the `p`-line, so the mapping is projection-agnostic.
- **Authoritative file: `<bucket>/phase_09_pto_canvas/pano.pto`** — `diff`-identical to
  `phase_10_warps/pano.pto`; includes committed manual tweaks and the **crop** `S<l>,<r>,<t>,<b>`.
  The delivered image is the crop region: Hillview rect (normalized) → ×(crop_w,crop_h) → +(l,t) →
  full canvas pixel before `pano_trafo`.
- **i-lines** carry `y p r` (yaw/pitch/roll), `v` (HFOV ≈7–30°, telephoto → ~0.14 m/px @10 km, so
  angular resolution isn't the limiter), distortion `a b c`, shift `d e`, and an **absolute** path
  `n"/var/data/tiff/<date>/…/phase_02_tiffs_fused/stack_NNNN.tif"` (a fused bracket).
- **Inversion: `pano_trafo -r pano.pto <image_n>`** (ships with Hugin; a subprocess, not custom
  lens math).
- **Per-frame geo:** the pano bucket has **0** `.geo.xmp`, but the **source date dir has them**
  (`2026-05-30/.../cr2/` had 16, keyed by CR2 stem incl. `AAAB7011`) + GPS CSVs → `geo-sidecar-fill`.
- **Placement:** `.pto`/CR2/geo/`pano_trafo` all live pics-side → pano work is a pics-side job that
  pushes only results.

**Verified end-to-end specimen:** gold pano **`c953f7df` = `grebovka/pano1`** — canvas crop
`S1518,69426,2034,7630` → 67908×5596 = its delivered dims; render meta `14.3999,50.0734, bearing
100.33, "Park Sacré Coeur"` matches its `14.400,50.073,compass 100`. `f0` rectilinear, 9 frames @
v10.5°, 13 hand-labels → the ideal first test of the whole chain.

**Residuals:** mapping quality depends on the `.pto`'s control-point optimization; a source "frame"
is a fused stack (members share a viewpoint → geo unambiguous); single-row horizontal baseline → no
multi-ring complications.

**Autocopy↔Hillview source map (verified 2026-06-15).** Full field notes:
[`pano-source-archaeology.md`](pano-source-archaeology.md). Pano source data spans **five pipeline
generations** (four numbered + a hand-Hugin tree) with incompatible layouts — `panoN/phase_12_exr_render/` (current), `pano/<range>/
phase_07_stitch/` (gen-2: prumyslovka, melnik-0ver), `panoN/render/*.exr.meta.json` with the EXR
cleaned (gen-3: karlin), and `span<N>/p_<range>-NN.pto` (gen-4: prosek, 2026-04-07) — plus a
hand-Hugin `hillview_eos/hugin/boranovice/` tree. Directory-based matching can't span these, so the
robust join is **frame-code tokens** (036A0457, AAAA3089…) shared between a photo's
`original_filename` and the `.pto`/`.exr`/`.meta` filenames (`scripts/enrich/pano_sources.py` →
`pano_sources.md`). `scripts/enrich/match_autocopy.py` complements it (workdir → `pano.pto` for
new-format panos, dims/geo, version-drift flags); `pano_inventory.py` reconciles the full DB side.

Result: **all 19 annotated panos have a located source** — stitched pixels (`.exr`), poses
(`.pto`), or CR2 frames. A fifth source class surfaced: **`hillview_eos/hugin/`**, a hand-Hugin
reservoir organized by location (prosek/vychod1, boranovice, čakovice, bohnice, ďáblicák, letňany,
silvestr, parukářka, kbely, kampa, …) — mostly 0-annotation today but a large stock of stitched
panos + `.pto`s for future targets and Track-B corpus. Its files often lack frame-range names, so
the robust join there is **crop-dims**: the `.pto` `p`-line `S<l>,<r>,<t>,<b>` gives delivered
`(r−l)×(b−t)`, matched to the photo's dims. Confirmed `333e8851` (88 annos, "Prosek east",
`original_filename`=`00.tiff`) = `…/prosek/DCIM/100EOS5D/vychod1/00_36A7584 - 18_36A7566.pto`
(`S377,67274,733,5866` → 66897×5133 ✓, f0). `575223fd` (Zbraslav) = `autocopy_todo_review/
2026-03-28_zbraslav/1/` CR2s. Projections **f0/f1/f2** all occur (rectilinear/cylindrical/
equirect) → always read the `p`-line. Pick the **newest** `.pto` when duplicates exist.

**Source frames as reconstruction input (vs slicing the delivery).** To pull a pano into the 3D
solve (`sfm-bundle` / MASt3R-SfM), feeding the delivered pano raw fails — MASt3R squashes everything
to 512 px, so a 66 k-wide pano becomes a smear. Two routes: (1) slice the delivery into overlapping
perspective sub-views (bakes in stitch errors), or (2) **use the original source frames** — real
perspective images (MASt3R-native), and the `.pto` `i`-lines already record each frame's solved
`y p r`/`v`, so the in-pano geometry is *written down*, not presumed. That makes the source set a
ready-made mini-reconstruction **and** a mutual cross-check (MASt3R's recovered poses vs the `.pto`
angles), and it dodges stitch artifacts (none in the Prosek panos; some in others). Cost: the
retrieve/redevelop pipeline above. Likely not worth it until panos enter the solve, but it's the
right shape when they do.

**Reference test case — the Prosek Rocks board (Doppelganger ground truth).** At the `333e8851`
vantage (Vyhlídka Prosecké skály) a physical info board prints a labelled panorama of the same
vista (`f05f60ee` frontal; `85d931b5` board + real skyline together). It is the decisive probe for
the reconstruction-driven thesis: a flat board ~1 m away whose pixels reproduce a km-deep scene —
a perfect 2D Doppelganger that MASt3R's 3D-grounding should expose as a coplanar near-plane.
Narrative + the GPS-cluster vs time-walk distinction: `docs/reconstruction-field-notes.md`.

---

## Appendix C — Reading list

Curated for the path above; each line says why it matters to us.

**Geometry foundations**
- *Multiple View Geometry in Computer Vision* — Hartley & Zisserman. The reference for epipolar
  geometry, triangulation, camera pose, bundle adjustment — the math under everything here.
- *Structure-from-Motion Revisited* — Schönberger & Frahm, 2016 (COLMAP). How poses + sparse 3D get
  solved from matches; the classical version of `sfm-bundle`.

**Features & matching (`feature-match`)**
- *Distinctive Image Features from Scale-Invariant Keypoints* — Lowe, 2004 (SIFT). The classical
  baseline, and why it breaks on big scale/viewpoint gaps.
- *SuperPoint* (DeTone 2018) → *SuperGlue* (Sarlin 2020) → *LightGlue* (Lindenberger 2023). Learned
  detection + matching; LightGlue is our default.
- *NetVLAD* — Arandjelović et al., 2016. Visual place recognition / image retrieval — the content
  side of the candidate `gate`.

**Feed-forward 3D (the backend + the 3D endgame)**
- *DUSt3R* (2023) → *MASt3R* / *MASt3R-SfM* (2024) → *VGGT* (CVPR 2025). The lineage replacing the
  classical pipeline with one forward pass; our M4 backend and the road to dense 3D.
  <https://vgg-t.github.io/>
- *MegaDepth* (Li & Snavely, 2018) and *MegaDepth-X* (2026). 3D/depth from sparse, noisy internet
  photo collections — the regime our corpus lives in. <https://megadepth-x.github.io/>

**Geolocation & our specifics**
- *Large-Scale Visual Geo-Localization of Images in Mountainous Terrain* — Baatz et al., 2012 (and
  PeakFinder). The skyline-matching idea behind `horizon-fit`.
- Hugin / panotools **PTO format** + **`pano_trafo`** docs. Practical reference for `pto-map` (App. B).
- *Nominatim* / *Photon* docs. Forward & reverse geocoding for `geocode-fwd`/`osm-reverse`.
