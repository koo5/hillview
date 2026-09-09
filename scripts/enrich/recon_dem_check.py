#!/usr/bin/env python3
"""What the DEM can and cannot say about a reconstruction's ground.

THE POINT, and the limit. A 2 m LiDAR DSM cannot tell you whether a 30 cm step in the
pavement is real — no elevation model at any resolution we have will settle a staircase
artefact. What it CAN settle is the low-frequency half: a span has exactly one free
vertical parameter (no photo here carries a GPS altitude, so the datum is unobservable
from inside), plus a slow tilt if the solve drifted. Both are long-baseline, and long
baselines are what a DEM is good for.

So this reports three numbers, in order of how much you should believe them:

  offset      the mean of (solved camera altitude) - (DEM ground + eye height). One free
              parameter per span, and the DEM fixes it outright.
  tilt        the slope of that residual along the track, in cm per 10 m. A real drift in
              the solve; also correctable, and worth knowing before it is.
  residual    what is left after removing both. This is where a staircase would live, and
              it is exactly where the DEM has nothing to say — a 2 m posting cannot see a
              step, so a large residual here is a question, not an answer.

Usage:  python recon_dem_check.py <run_id_or_dir> [--dsm /dem/cuzk/dsm2.vrt] [--eye 1.5]
Runs inside the terrain worker container, which has rasterio and the /dem mount:
  docker exec enrich_terrain_worker python /work/recon_dem_check.py ...
"""
import argparse
import json
import math
import os
import sys

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metadata", help="path to a run's metadata.json")
    ap.add_argument("--dsm", default="/dem/cuzk/dtm10.vrt")
    ap.add_argument("--eye", type=float, default=1.5, help="assumed camera height, m")
    ap.add_argument("--renderer", default="/work/renderer.py")
    a = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(a.renderer)))
    import renderer  # noqa: E402

    md = json.load(open(a.metadata))
    frames = md["frames"]
    al = md["alignment"]
    s, R, t = al["scale_units_per_m"], np.array(al["R"]), np.array(al["t"])
    alt0 = float(al.get("alt0") or 0.0)
    poses = np.array([f["pose_cam2world"] for f in frames], dtype=float)
    cams = s * (poses[:, :3, 3] @ R.T) + t          # ENU metres, U relative to alt0
    lat = np.array([f["gps"][0] for f in frames])
    lon = np.array([f["gps"][1] for f in frames])
    lat0, lon0 = md["center"]

    grid = renderer.load_geotiff_window(a.dsm, lat0, lon0, radius_m=2000.0)
    ground = grid.sample(lat, lon)
    ok = np.isfinite(ground)
    if ok.sum() < 4:
        print(f"DEM has no coverage here ({a.dsm})")
        return
    print(f"{ok.sum()}/{len(frames)} frames inside {os.path.basename(a.dsm)} "
          f"(cell {grid.cell_size_m(lat0):.1f} m)")

    # the solve says the camera is this far above the DEM's ground, in DEM datum terms
    resid = (cams[ok, 2] + alt0) - (ground[ok] + a.eye)
    kx = 111320.0 * math.cos(math.radians(lat0))
    e = (lon[ok] - lon0) * kx
    n = (lat[ok] - lat0) * 110540.0
    # ARCLENGTH in capture order, not distance-from-the-first-frame: a walk that curves or
    # doubles back would otherwise fold onto itself and the fitted tilt would be nonsense.
    step = np.hypot(np.diff(e), np.diff(n))
    d = np.concatenate([[0.0], np.cumsum(step)])
    r = resid
    A = np.column_stack([d, np.ones(len(d))])
    slope, intercept = np.linalg.lstsq(A, r, rcond=None)[0]
    flat = r - (A @ [slope, intercept])
    print(f"  track length {d.max():.0f} m")
    print(f"  offset   {np.mean(resid):+8.2f} m   (the datum: one free parameter, fixable)")
    print(f"  tilt     {slope * 1000:+8.2f} cm per 10 m along track "
          f"({slope * d.max():+.2f} m end to end)")
    print(f"  residual  {flat.std():8.2f} m sd, p90 |{np.percentile(np.abs(flat), 90):.2f}| m"
          f"   <- the DEM cannot judge this")
    print(f"  ground along track: {ground[ok].min():.1f}..{ground[ok].max():.1f} m "
          f"(relief {np.ptp(ground[ok]):.1f} m)")


if __name__ == "__main__":
    main()
