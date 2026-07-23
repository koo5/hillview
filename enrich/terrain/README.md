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
| `worker.py` | RabbitMQ worker (untrusted topology, cf. `matcher/`): renders against a local DEM, POSTs artifacts back with a token |
| `run_worker.sh` | systemd transient unit with memory ceiling (same belt-and-braces as the matcher) |
| `test_renderer.py` | synthetic-terrain tests — horizon dip, peak bearing/depth, curvature+refraction, occlusion, codec, window clipping, datum resolution |
| `make_fixture.py` | deterministic e2e fixtures + the cross-language `golden.json` contract |
| `../web/tests-playwright/` | Playwright bench suite (route-stubbed API, software-GL chromium) |
| `../api/app/routers/terrain.py` | enqueue / result callback / artifact serving; `terrain_renders` in `../db/init/006_terrain.sql` |
| `../web/src/routes/terrain/` | bench chrome: enqueue form, render list, fog controls, pick panel |
| `../../shared/terrain/` | **the viewer itself** — dependency-free `DepthPanoViewer` (WebGL fog, wheel/drag/pinch, click-back), consumed by the bench AND the main app |
| `../../frontend/src/lib/components/TerrainViewer.svelte` | main-app wrapper around the shared core, ready for the photo pane |

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

```bash
# schema lands on API restart (idempotent init SQL)
docker compose up -d --build api web

# worker, in any venv with numpy+rasterio+pillow+psutil+remoulade+requests:
export TERRAIN_DSM_PATH="/data/dem/dsm10.vrt@15000:/data/dem/dsm_far.vrt"
export TERRAIN_DTM_PATH="/data/dem/dtm10.vrt"
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
