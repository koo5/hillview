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
| `renderer.py` | pure-numpy core: DEM grid, vectorised horizon march, click-back, preview shading, depth codec |
| `worker.py` | RabbitMQ worker (untrusted topology, cf. `matcher/`): renders against a local DEM, POSTs artifacts back with a token |
| `run_worker.sh` | systemd transient unit with memory ceiling (same belt-and-braces as the matcher) |
| `test_renderer.py` | synthetic-terrain tests — horizon dip, peak bearing/depth, curvature+refraction, occlusion, codec |
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

## DEM mosaic (`TERRAIN_DEM_PATH`)

The worker wants one north-up EPSG:4326 raster (COG or VRT). Suggested build:

1. **ČÚZK DMP 1G** (surface model — canopy and buildings form the real
   skyline; open data CC BY 4.0): download sheets for the area of interest
   from the ČÚZK Geoportal (ATOM feeds), then
   `pdal pipeline` → rasterize to DSM GeoTIFFs (S-JTSK / EPSG:5514, Bpv heights).
2. `gdalwarp -t_srs EPSG:4326` each sheet (this also handles the
   Bpv→ellipsoidal question well enough for rendering: we only compare
   heights against each other, so a consistent vertical datum suffices).
3. **Copernicus GLO-30** tiles for the ring beyond the borders
   (Šumava viewpoints see Bavaria and Austria).
4. `gdalbuildvrt mosaic.vrt cz_*.tif glo30_*.tif` (finest-resolution-first),
   optionally `gdal_translate -of COG` for one tidy file.

Resolution strategy: full DMP 1G resolution is overkill beyond ~10 km
(angular size of a 1 m cell at 10 km ≈ 0.006°, an eighth of a pixel at our
default 0.05° grid) — a 10 m near / 30 m far composite keeps the windowed
read around 200 MB per render.

Practical DSM caveat: the observer often stands *under* the surface model
(canopy). When the photo has GPS altitude the API passes it as
`observer_elevation_m` (+1.6 m eye height); otherwise the renderer uses
DSM + `observer_height_m` and viewpoints in forests will need a manual nudge.

## Run

```bash
# schema lands on API restart (idempotent init SQL)
docker compose up -d --build api web

# worker, in any venv with numpy+rasterio+pillow+psutil+remoulade+requests:
export TERRAIN_DEM_PATH=/data/dem/mosaic.vrt
cd enrich/terrain && ./run_worker.sh

# tests (no data / rasterio needed)
python -m pytest enrich/terrain/test_renderer.py -q
```

Then the **Terrain** tab in the bench: enqueue by photo id or ad-hoc lat/lon,
pick the finished render, drag the visibility slider, click a mountain.

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
