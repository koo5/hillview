# Terrain data licensing — obligations and how we discharge them

Status: researched 2026-07-27 (licence texts read, not lawyer-reviewed). The
terrain renders are **derived works of the DEMs they march**, so the data
licences follow the artifacts (`depth.bin`, `preview.jpg`, and anything shown
in the viewers) wherever they are displayed, served, or redistributed — the
obligations don't stay behind in the worker.

Mechanism in one line: the worker stamps `TERRAIN_ATTRIBUTION` into every
render's `meta.attribution` (`enrich/terrain/worker.py`), the viewers display
it (`frontend/src/lib/components/TerrainPane.svelte` statusbar), and the
containerized auto-GLO-30 path defaults the env to the required Copernicus
notice (`enrich/terrain/docker-entrypoint.sh`). Attribution is data carried
by each render, not UI copy — a render made from different sources carries a
different notice, and old renders keep the notice that was true when they
were made.

## Copernicus GLO-30 (the auto-downloaded DSM)

Source: AWS open data bucket `copernicus-dem-30m`, fetched by
`enrich/terrain/download_glo30.py`. Licence: **"Licence for Copernicus DEM
instance COP-DEM-GLO-30-F Global 30m Full, Free & Open"** (EU/ESA; the data
itself is © DLR and Airbus — IPR is *not* relinquished, we are sublicensees).
Licence text:
<https://docs.sentinel-hub.com/api/latest/static/files/data/dem/resources/license/License-COPDEM-30.pdf>
(mirror; the canonical home is the Copernicus space data portal,
spacedata.copernicus.eu, under the Copernicus DEM collection).

Rights granted (Art. 4): reproduction, distribution, communication to the
public, adaptation/modification/combination — worldwide, perpetual, free of
charge, commercial use included. No "non-commercial" trap. The obligations
are all in Art. 6:

* **6(b) — our case (adapted/modified data).** Renders must carry this exact
  notice:

  > produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus
  > Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
  > European Union and ESA; all rights reserved

  Discharged: this is the entrypoint's `TERRAIN_ATTRIBUTION` default, so it
  rides in `meta.attribution` and the terrain pane displays it under the
  viewer.

* **6(a) — distributing the *data* itself.** Same notice minus the "produced
  using" prefix. Only relevant if we ever serve DEM tiles or elevation
  rasters onward (we don't today; the depth buffer is a render, 6(b)
  territory).

* **6(c) — liability sentence when distributing/communicating to the
  public.** The covering licence / legal notice / terms of whatever channel
  publishes the renders must include:

  > The organisations in charge of the Copernicus programme by law or by
  > delegation do not incur any liability for any use of the Copernicus
  > WorldDEM-30

  **Not yet discharged** — nothing is public yet (the workbench binds
  loopback). This sentence must land in the app's terms/legal page in the
  same release that first shows terrain renders to real users.

* **6(d) — no implied endorsement.** Don't present the app as endorsed by
  Copernicus/ESA/Airbus. Satisfied by not doing marketing with their logos;
  note the licence grants **no logo rights** at all (Art. 9) — text notices
  only, and the WorldDEM trademark may only be used in notices like the
  above.

* **6(e) — obligations propagate.** If we let third parties redistribute
  renders (API consumers, downloads), we must pass these obligations on to
  them — a line in the API terms when that day comes.

Breach ⇒ the licensor may terminate all rights (Art. 9/Termination), so the
notice is load-bearing, not decorative.

## ČÚZK DMP 1G / DMR 5G (the planned fine near-ring mosaics)

Source: ČÚZK ATOM services via `enrich/terrain/download_cuzk.py`; not yet
feeding any worker. Licence: **CC BY 4.0** per ČÚZK's open-data terms
(in force since July 2023; also asserted in `build_mosaic.py`'s docstring).
*Caveat: the geoportal was unreachable when this doc was researched — re-read
their current conditions page before the first public release that uses this
data.*

Obligation: attribution ("© ČÚZK") plus the usual CC BY hygiene (link the
licence, indicate if modified — a rasterized/warped mosaic is modified).
Plan: when ČÚZK mosaics feed a worker, set that worker's
`TERRAIN_ATTRIBUTION` to a combined notice, e.g.:

    © ČÚZK (DMP 1G, CC BY 4.0) · produced using Copernicus WorldDEM-30 © DLR
    e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided
    under COPERNICUS by the European Union and ESA; all rights reserved

(the GLO-30 notice stays as long as GLO-30 remains the far/borders layer of
the composite — `TERRAIN_DSM_PATH="mosaic/dsm10.vrt@15000:mosaic/dsm_far.vrt"`
composites both).

## OSM peak labels (Overpass `natural=peak`)

Source: `GET /api/terrain/peaks` (`enrich/api/app/routers/terrain.py`)
querying Overpass. Licence: **ODbL** — display "© OpenStreetMap
contributors" wherever the peak data is shown.

Discharged: the terrain pane appends "peaks © OpenStreetMap contributors" to
the attribution line whenever peak candidates are loaded. This is separate
from (and additional to) the Leaflet map-tile attribution — the panorama
viewer is not the map, so it can't borrow the map's credit line.

## Checklist

| obligation | where it must appear | status |
|---|---|---|
| GLO-30 6(b) notice on renders | viewer UIs, via `meta.attribution` | **done** (frontend pane; entrypoint default) |
| GLO-30 6(c) liability sentence | app terms / legal page | **TODO before renders go public** |
| GLO-30 6(e) pass-through | API/download terms | TODO if artifacts become redistributable |
| ČÚZK CC BY credit | `TERRAIN_ATTRIBUTION` of ČÚZK-fed workers | TODO when those mosaics exist (+ re-verify terms) |
| OSM ODbL peaks credit | next to peak labels | **done** (frontend pane) |
| bench (enrich/web) attribution display | bench terrain page | open — loopback-only today, so no public communication happens there |

Related: `enrich/terrain/README.md` § Licensing / attribution (summary),
`docs/terrain-mode.md` (graduation plan — step "(1) main backend serves the
two artifacts" is the moment 6(c) and the API-terms items activate).
