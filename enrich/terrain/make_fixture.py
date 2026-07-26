#!/usr/bin/env python3
"""Generate the deterministic terrain fixtures the Playwright suite serves via
route stubs (no worker, no RabbitMQ, no gdal): preview.jpg + depth.bin +
meta.json + golden.json.

golden.json is the CROSS-LANGUAGE contract: pixel coordinates chosen here and
the geo coordinates Python computes for them (renderer.pixel_to_latlon). The
browser suite clicks those pixels and asserts the TypeScript click-back
(shared/terrain pickFromDepth) agrees within epsilon — pinning renderer ↔
viewer forever. depth.bin/meta.json are bit-deterministic (pure numpy on an
analytic scene); preview.jpg is only a backdrop and never pixel-compared.

Scene (viewpoint 50.0N 14.5E, eye 302 m, looking 60°–120°):
  * "summit":   800 m peak at bearing 90°, 25 km — the golden click target
  * "far ridge": 500 m ridge at bearing 105°, 55 km — the fog-physics probe
  * near slope: gentle rise close in at bearing 75° — the fog control pixel

Regenerate (from enrich/terrain/):  python3 make_fixture.py
Output: ../web/tests-playwright/fixtures/
"""
from __future__ import annotations

import io
import json
import math
import os

import numpy as np

import renderer

OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "web", "tests-playwright", "fixtures"))
LAT0, LON0 = 50.0, 14.5
M_PER_DEG_LAT = 111_320.0


def build_scene() -> renderer.DemGrid:
    cell = 150.0
    half = 70_000.0
    n = int(2 * half / cell) + 1
    dlat = cell / M_PER_DEG_LAT
    dlon = cell / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))
    rows = LAT0 + (n // 2) * dlat - np.arange(n) * dlat
    cols = LON0 - (n // 2) * dlon + np.arange(n) * dlon
    elev = np.full((n, n), 300.0, np.float32)

    def bump(bearing, dist, height, sigma):
        plat, plon = renderer.destination_point(LAT0, LON0, bearing, dist)
        dy = (rows[:, None] - plat) * M_PER_DEG_LAT
        dx = (cols[None, :] - plon) * M_PER_DEG_LAT * math.cos(math.radians(LAT0))
        elev[:] += (height * np.exp(-(dx**2 + dy**2) / (2 * sigma**2))).astype(np.float32)

    bump(90.0, 25_000.0, 800.0, 1_200.0)    # summit — the click target
    bump(105.0, 55_000.0, 500.0, 2_500.0)   # far ridge — fog probe
    bump(75.0, 4_000.0, 80.0, 600.0)        # near hill — fog control (tight:
                                             # must not leak under the viewpoint)
    return renderer.DemGrid(elev=elev, lat_top=float(rows[0]),
                            lon_left=float(cols[0]), dlat=dlat, dlon=dlon)


def top_visible(pano: renderer.Panorama, az_deg: float) -> tuple[int, int]:
    j = int(np.argmin(np.abs(pano.azimuths - az_deg)))
    return j, int(np.argmax(np.isfinite(pano.depth[:, j])))


def main() -> None:
    dem = build_scene()
    pano = renderer.render(dem, LAT0, LON0, observer_elevation_m=302.0,
                           az_start=60.0, az_end=120.0, az_step_deg=0.1,
                           elev_min_deg=-1.5, elev_max_deg=2.5, elev_step_deg=0.02,
                           min_distance_m=300.0, max_distance_m=70_000.0)
    os.makedirs(OUT, exist_ok=True)

    with open(os.path.join(OUT, "depth.bin"), "wb") as f:
        f.write(renderer.encode_depth_u16(pano.depth))
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(pano.meta(), f, indent=1)

    from PIL import Image                       # backdrop only, never compared
    buf = io.BytesIO()
    Image.fromarray(renderer.shade(pano)).save(buf, "JPEG", quality=85)
    with open(os.path.join(OUT, "preview.jpg"), "wb") as f:
        f.write(buf.getvalue())

    # golden picks — quantise depth exactly the way the browser will see it
    def golden_pick(az):
        col, row = top_visible(pano, az)
        row = min(row + 2, pano.depth.shape[0] - 1)     # 2 px below the crest: stable
        q = round(float(pano.depth[row, col]) / renderer.DEPTH_SCALE_M)
        d = q * renderer.DEPTH_SCALE_M
        plat, plon = renderer.destination_point(LAT0, LON0,
                                                float(pano.azimuths[col]), d)
        return {"col": col, "row": row, "lat": float(plat), "lon": float(plon),
                "distance_m": d, "azimuth_deg": float(pano.azimuths[col])}

    sky_col = int(np.argmin(np.abs(pano.azimuths - 65.0)))
    golden = {
        "viewpoint": {"lat": LAT0, "lon": LON0},
        "summit": golden_pick(90.0),
        "far_ridge": golden_pick(105.0),
        "near_slope": golden_pick(75.0),
        "sky": {"col": sky_col, "row": 2},
        "tolerance_deg": 2e-4,                  # ~22 m — float32 vs float64 headroom
    }
    with open(os.path.join(OUT, "golden.json"), "w") as f:
        json.dump(golden, f, indent=1)
    print(f"fixtures → {OUT}")
    print(f"  grid {pano.depth.shape[1]}x{pano.depth.shape[0]}, "
          f"summit @ col {golden['summit']['col']} "
          f"depth {golden['summit']['distance_m']/1000:.1f} km, "
          f"far ridge {golden['far_ridge']['distance_m']/1000:.1f} km, "
          f"near slope {golden['near_slope']['distance_m']/1000:.1f} km")


if __name__ == "__main__":
    main()
