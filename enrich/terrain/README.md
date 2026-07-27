# Terrain workstream — synthetic depth panoramas

Renders what the terrain *should* look like from a photo's viewpoint, out to
~100 km, with a per-pixel **depth channel**. The depth channel is the product:

* **live fog** — the bench viewer applies Koschmieder fog
  (`1 − exp(−3.912·d/V)` for visibility `V`) in a fragment shader; sliders
  re-shade instantly, nothing is re-rendered;
* **click-back** — a pixel is `(azimuth, depth)`; the forward geodesic (same
  spherical math as `frontend/src/lib/geo.ts`) turns a click on a mountain
  into its geo coordinates;
* **auto-annotation feed (next)** — skyline/depth extrema × OSM `natural=peak`
  ⇒ candidate facts for the …→ anchoring → matching → **3D** pipeline.

## Pieces

| file | role |
|---|---|
| `renderer.py` | pure-numpy core: DEM grids (+`CompositeDem` layering), vectorised horizon march, observer/datum resolution, click-back, preview shading, depth codec |
| `build_mosaic.py` | DSM/DTM mosaic builder — pdal/gdal CLI wrapper with `--dry-run`, command construction unit-tested |
| `download_cuzk.py` | whole-CZ bulk downloader for the ČÚZK ATOM services (stdlib-only, resumable, polite), parsing pinned to real service XML |
| `download_glo30.py` | Copernicus GLO-30 tile downloader for a bbox (stdlib-only, resumable) — the containerized worker's auto-DSM and the far/borders layer of the full flow |
| `Dockerfile` + `docker-entrypoint.sh` | containerized worker (compose service `terrain-worker`): auto-downloads GLO-30 for `TERRAIN_AUTO_DEM_BBOX` into the `terrain_dem` volume, stitches a VRT, runs |
| `worker.py` | RabbitMQ worker (untrusted topology, cf. `matcher/`): renders against a local DEM, POSTs artifacts back with a token |
| `run_worker.sh` | systemd transient unit with memory ceiling (same belt-and-braces as the matcher) |
| `test_renderer.py` | synthetic-terrain tests — horizon dip, peak bearing/depth, curvature+refraction, occlusion, codec, window clipping, datum resolution |
| `make_fixture.py` | deterministic e2e fixtures + the cross-language `golden.json` contract |
| `../web/tests-playwright/` | Playwright bench suite (route-stubbed API, software-GL chromium) |
| `../api/app/routers/terrain.py` | enqueue / result callback / artifact serving; `terrain_renders` in `../db/init/006_terrain.sql` |
| `auto_cuzk.sh` | bbox-scoped ČÚZK build (fetch → pdal rasterize → 2 m + 10 m warp rings → vrt), incremental; whole-republic prefetch = same script, CZ bbox |
| `../web/src/routes/terrain/` | bench: viewer-first layout (overlay toolbar, fullscreen, title search, mobile), enqueue form with labeled fields + help |
| `../web/src/routes/terrain/overlay/` | EXPERIMENT: render skyline overlaid on the source pano — horizontal from the pie, vertical manually aligned (candidate future vertical calibration) |
| `../../shared/terrain/` | **the viewer** — dependency-free `DepthPanoViewer` core (WebGL fog, zoom/pan/pinch, click-back, compass, sector clamp) + the SHARED `TerrainViewer.svelte` wrapper (labels, exaggeration, overlays) consumed by the bench AND the main app |

## The two accuracy terms

At 100 km, flat-earth rendering is off by a skyline's worth:

* **curvature** lowers a target by `d²/(2R)` — ~590 m at 100 km;
* **refraction** lifts it partly back: effective radius `R' = R/(1−k)`,
  `k ≈ 0.13` standard conditions (tunable per render — cold clear mornings
  run higher, which is exactly when the Alps photobomb Šumava).

Both live in one expression: `angle = atan((h − h_eye)/d − d/(2R'))`,
verified against closed forms in the tests.

## Algorithm

March a shared, geometrically growing distance schedule (near steps ≈ DEM
cell, far steps ≈ 0.5 % of distance). At each distance, sample the DEM at
every azimuth at once (one bilinear gather), record apparent elevation
angles. `np.maximum.accumulate` over distance gives the horizon
profile-so-far; per column, one `searchsorted` maps pixel rows (elevation
angles) to the first march step that reaches them — that step's distance is
the pixel's depth. 360°×20° at 0.05° over 55 km: ~1.2 s single-core.

## Artifacts

* `preview.jpg` — hypsometric shaded RGB, **no fog baked in**
* `depth.bin` — row-major little-endian uint16, `depth_m = value·4`, `0` = sky
  (raw on purpose: browser canvases truncate 16-bit PNG to 8 bits; a raw
  buffer goes straight into `Uint16Array` → WebGL `R32F` texture)
* `meta` (jsonb on `terrain_renders`) — grid geometry, viewpoint, params

## DEM mosaics (`TERRAIN_DSM_PATH`, `TERRAIN_DTM_PATH`)

Raw data first — the whole country, resumably:

```bash
python3 download_cuzk.py fetch --dataset dmp1g --out /data/dl/dmp1g --unzip   # surface
python3 download_cuzk.py fetch --dataset dmr5g --out /data/dl/dmr5g --unzip   # bare earth
# smoke test a small area first: --bbox 14.2,49.9,14.7,50.2 --limit 20
```

It walks the verified ATOM contract (dataset feed → per-sheet feeds →
`openzu.cuzk.gov.cz` ZIPs, whose dated filenames must be RESOLVED, never
constructed), caches resolved URLs into `index.json`, skips complete files
by advertised size, and defaults to 4 polite workers. Fair warning: whole-CZ
DMP 1G + DMR 5G is tens of thousands of sheets and hundreds of GB — plan the
disk and let it run overnight; reruns only fetch what's missing.

Two rasters, two jobs: the **DSM** (surface — canopy and buildings form the
real skyline) is what the rays march; the **DTM** (bare earth) is what the
OBSERVER stands on — grounding on a surface model means standing on canopy.
`build_mosaic.py` builds both (rasterize → warp → vrt; see its docstring for
the full ČÚZK DMP 1G / DMR 5G / Copernicus GLO-30 flow), and each env var
takes colon-separated layers, finest first, each optionally capped:

```bash
export TERRAIN_DSM_PATH="mosaic/dsm10.vrt@15000:mosaic/dsm_far.vrt"
export TERRAIN_DTM_PATH="mosaic/dtm10.vrt"
```

The `@radius_m` cap is the resolution-ring story (full DMP 1G detail is
overkill beyond ~10 km: a 1 m cell at 10 km subtends ~0.006°, an eighth of a
pixel at the default 0.05° grid) and `CompositeDem` (first finite sample
wins) is also the borders story — fine ČÚZK data inside CZ, GLO-30 where
Šumava looks into Bavaria. A 10 m near / 30 m far composite keeps the
windowed read around 200 MB per render. Windows are clipped to each raster's
extent (an overhanging read would otherwise be silently mis-georeferenced —
regression-tested).

## Render defaults & knobs (2026-07)

What a plain enqueue does, and which allowlisted params change it
(`ALLOWED_PARAMS` in the API, `RENDER_KEYS` + stack env in the worker —
defense on both ends):

* **Grid**: 0.025° in both axes (worker `setdefault`; the renderer's own
  default stays 0.05°). UI rungs: 0.1° / 0.05° / 0.025° / sector ×10
  (0.005°, 36°) / sector ×20 (0.0025°, 18°). Sectors exist because a full
  360° at ×10 would be a 72k-column texture — beyond GPU limits; each rung
  keeps the same 7200-column artifact over a narrower `az_start..az_end`.
* **Elevation window**: auto-fit when not explicit — a coarse probe (1°
  azimuth, ~5% cost) finds the horizon; top clamps to it + 1.5° (sky
  headroom for labels), bottom trims rows that are pure near-field
  (every column < 300 m), capped at 4000 rows (mobile GPU texture limit).
  Provenance in `meta.elev_fit`.
* **Photo enqueues**: viewpoint + EXIF-altitude hint from `photo_mirror`;
  the azimuth sweep is limited to the photo's pie — calibrated
  centre/FOV when a calibration exists, compass ± 45° assumed otherwise,
  ± 5° margin; wedges covering the full circle fall back to 360°.
* **DEM stacks** (`dsm_stack` param): `auto` = the worker default, which
  the entrypoint promotes to the ČÚZK composite where built
  (2 m ring @ 4 km → 10 m @ 15 km → GLO-30; bare-earth DTM grounding);
  `glo30` forces the 30 m model alone (source comparison); `cuzk` names
  the composite explicitly. Per-stack attribution rides `meta.attribution`.
* **Near field**: `min_distance_m` (default 50) clips the march start —
  useful at ~300 for vista comparison, since sub-50 m objects are
  data-limited anyway (one or two cells → giant interpolated slabs) —
  but note clipped obstacles no longer occlude.
* **Label candidates** (`/terrain/peaks`): UNCAPPED Overpass pool — named
  `natural=peak` ∪ observation towers/communication masts — with missing
  `ele` filled by sampling the DSM (flagged `ele_estimated`), `prominence`
  passed through (client label priority), identifying User-Agent, and
  Overpass `remark` (abort) detection; cached 7 d per ~1 km grid.
* **Queue feedback**: `/terrain/renders` carries RabbitMQ
  `{messages, consumers}` so the UIs can say "no worker connected".

Viewer (the SHARED `shared/terrain/TerrainViewer.svelte`, mounted by both
apps): responsive fill, cursor-anchored wheel/pinch zoom, sector pan
clamping, vertical exaggeration (display-only), compass ruler, sky-anchored
clickable peak labels (prominence-first, per-column-neighborhood thinning,
depth-match tolerance slider), sky-click → horizon snap, initial view
centered on the measured terrain band.

## Observer elevation: the datum problem

Phone EXIF altitude doesn't say whether it's ellipsoidal or orthometric, and
in Czechia the geoid undulation (~44.5 m, `TERRAIN_GEOID_OFFSET_M`) is
exactly a rozhledna's worth of ambiguity. So GPS altitude flows through the
API as a HINT (`gps_altitude_m`, optional `gps_datum`), and the worker
resolves it against the DTM ground (`renderer.resolve_eye_elevation`):
plausibility first (both interpretations must land within
0.5–60 m above bare ground), proximity to eye height second, implausible
fixes rejected in favour of ground + `observer_height_m`. The outcome is
recorded in `meta.eye_source` (`gps-orthometric`,
`gps-ellipsoidal-corrected`, `gps-rejected`, `terrain+eye`, `explicit`) with
`ground_m`/`ground_source` alongside — every skyline knows where its eye
came from. Known residual ambiguity: a ~44 m tower with a true orthometric
fix reads as an ellipsoidal ground fix; the ground interpretation wins as
the far more common case.

## Run

The zero-setup path is the **containerized worker** — first start downloads
the GLO-30 tiles for `TERRAIN_AUTO_DEM_BBOX` (default: CZ + margin, ~2 GB,
one-time into the `terrain_dem` volume), stitches a VRT and consumes the
`terrain` queue:

```bash
docker compose up -d --build terrain-worker
docker logs -f enrich_terrain_worker
```

30 m surface data is plenty for far skylines. The fine ČÚZK near ring is a
second auto path: set `TERRAIN_AUTO_CUZK_BBOX` (see `.env.example`) and the
entrypoint downloads the DMP 1G + DMR 5G sheets for that bbox, rasterizes
(pdal, 2 m), warps to the 10 m near ring and exposes it as the `cuzk` stack —
a composite with the default DSM beyond 15 km / outside the bbox. Every stage
is incremental, so growing the bbox later only adds sheets; the whole-republic
overnight prefetch is the SAME machinery run detached (plan hundreds of GB —
zips + laz + rasters stay in the volume for resumability, ~3-4× the download):

```bash
docker compose run --rm --entrypoint sh terrain-worker \
    auto_cuzk.sh "12.09,48.55,18.87,51.06"   # CZ-wide; resumable, rerun anytime
```

Prefer pre-built mosaics? Mount them and set
`TERRAIN_DSM_PATH`/`TERRAIN_DTM_PATH` (or the `_CUZK` stack variants) — or
run the host-side worker instead:

```bash
# schema lands on API restart (idempotent init SQL)
docker compose up -d --build api web

# worker deps are hash-pinned (requirements.txt, compiled from requirements.in)
# — provision the venv once:
uv pip install -p ../../scripts/enrich/.venv/bin/python --require-hashes -r requirements.txt
#   (plain pip works too: pip install --require-hashes -r requirements.txt)
export TERRAIN_DSM_PATH="/data/dem/dsm10.vrt@15000:/data/dem/dsm_far.vrt"
export TERRAIN_DTM_PATH="/data/dem/dtm10.vrt"
# remote boxes also set TERRAIN_CALLBACK_URL + ENRICH_WORKER_TOKEN — the
# callback and token come from worker env, never from the queue message
cd enrich/terrain && ./run_worker.sh

# python tests (no data / rasterio needed)
python -m pytest enrich/terrain -q

# bench e2e (route-stubbed — no backend/worker/rabbit; needs a browser once:
#   cd enrich/web && npx playwright install chromium)
cd enrich/web && npm run test:e2e
# fixtures regenerate deterministically (depth.bin/meta/golden are bit-stable):
python3 ../terrain/make_fixture.py
```

Then the **Terrain** tab in the bench: enqueue by photo id or ad-hoc lat/lon,
pick the finished render, drag the visibility slider, click a mountain.

## Licensing / attribution

Full obligations write-up (exact required notices, what's discharged where,
the pre-launch checklist, licence-text link): **`docs/terrain-data-licensing.md`**.
Summary:

The rendered artifacts are derived works of the DEMs, so the data licences
follow the renders wherever they are shown. The worker stamps
`TERRAIN_ATTRIBUTION` into each render's `meta.attribution` and the viewers
display it; the containerized auto-GLO-30 path defaults it to the required
Copernicus notice — set it yourself when other sources feed the mosaics.

* **Copernicus GLO-30** (Licence for COP-DEM-GLO-30, Art. 6(b) — adapted /
  modified data): *"produced using Copernicus WorldDEM-30 © DLR e.V.
  2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved"*.
  Publishing renders to the general public additionally requires (Art. 6(c))
  this sentence in the covering legal notice / terms: *"The organisations in
  charge of the Copernicus programme by law or by delegation do not incur any
  liability for any use of the Copernicus WorldDEM-30"*.
* **ČÚZK DMP 1G / DMR 5G** — CC BY 4.0: credit "© ČÚZK" once mosaics built
  from them feed the worker (fold it into `TERRAIN_ATTRIBUTION`).
* **OSM peak labels** — ODbL: the viewer shows "peaks © OpenStreetMap
  contributors" whenever peak candidates are displayed.

## E2E: the golden thread

`make_fixture.py` renders a synthetic scene (summit 25 km / far ridge 54 km /
near hill 4 km) and writes `golden.json`: pixel targets plus the geo
coordinates the PYTHON renderer computes for them. The Playwright suite
serves those artifacts through route stubs, clicks the pixels, and asserts
the TypeScript click-back agrees within ~22 m — if `renderer.py` and
`shared/terrain` ever drift, this goes red. The same suite checks fog is
Koschmieder-shaped (far ridge swallowed, near hill barely moves), that
click-back survives cursor-anchored zoom, and the enqueue→done lifecycle
with a simulated worker. `DepthPanoViewer.readPixel()` is the
instrumentation hook (synchronous redraw+read, no preserveDrawingBuffer).

## Reuse in the main app

The viewer follows the `$zoomview` sharing pattern: the core lives in
repo-root `shared/terrain/` (vanilla TS, no Svelte/stores/$lib), aliased as
`$terrain` in both apps (frontend `svelte.config.js` kit.alias + generated
tsconfig; enrich/web vite alias + manual tsconfig paths), its pure pick math
unit-tested from the frontend's vitest (`../shared/terrain/**` include), and
COPYied by the enrich/web Dockerfile like `shared/zoomview`.

`frontend/src/lib/components/TerrainViewer.svelte` is the app-facing wrapper:
`previewUrl` + `depthUrl` + `meta` in, `onpick` (geo coords) out, bindable
`visibilityKm`/`skyColor`, touch-ready (Pointer Events pinch in the core).
Graduation path to the photo pane: (1) main backend serves the two artifacts
per photo (next to the pyramids), (2) `Photo.svelte` grows a terrain mode
beside the OSD/Pannellum switch, (3) `onpick` flies the Leaflet map. The
workbench stays the place where renders are produced and curated.
