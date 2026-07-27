#!/usr/bin/env python3
"""Bulk-download Copernicus GLO-30 DSM tiles (AWS open data, CC-BY-like ESA
licence, no auth) for a lon/lat bbox — the terrain worker's auto-DSM path
(docker-entrypoint.sh), and the "far ring / across the border" layer of the
full ČÚZK flow (build_mosaic.py). Stdlib-only, like download_cuzk.py.

Tiles are 1°×1° EPSG:4326 COGs named by their SW corner on the public bucket:

    https://copernicus-dem-30m.s3.amazonaws.com/
        Copernicus_DSM_COG_10_N50_00_E014_00_DEM/
            Copernicus_DSM_COG_10_N50_00_E014_00_DEM.tif

Ocean tiles simply don't exist (404 → noted, skipped). Reruns skip local
files whose size matches the bucket's Content-Length, so a volume fills once
and later starts only HEAD-check.

    python3 download_glo30.py --bbox 11.5,47.5,19.5,51.5 --out /dem/glo30
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
RETRIES = 3


# ---------------------------------------------------------------------------
# tile arithmetic (pure — unit-tested without network)
# ---------------------------------------------------------------------------

def tiles_for_bbox(w: float, s: float, e: float, n: float) -> list[tuple[int, int]]:
    """SW corners (lat, lon) of the 1° tiles covering [w,e]×[s,n]; an edge
    landing exactly on a tile boundary does not drag in the next tile."""
    return [(lat, lon)
            for lat in range(math.floor(s), max(math.floor(s) + 1, math.ceil(n)))
            for lon in range(math.floor(w), max(math.floor(w) + 1, math.ceil(e)))]


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def tile_url(lat: int, lon: int) -> str:
    name = tile_name(lat, lon)
    return f"{BUCKET}/{name}/{name}.tif"


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

def _remote_size(url: str) -> int | None:
    """Content-Length via HEAD, None for a missing (ocean) tile."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return int(r.headers["Content-Length"])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_tile(lat: int, lon: int, out_dir: str) -> tuple[str, str]:
    """→ (tile_name, 'ok'|'kept'|'ocean'). Downloads land as .part first so a
    killed run never leaves a truncated .tif that a rerun would 'keep'."""
    name, url = tile_name(lat, lon), tile_url(lat, lon)
    dest = os.path.join(out_dir, f"{name}.tif")
    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            size = _remote_size(url)
            if size is None:
                return name, "ocean"
            if os.path.exists(dest) and os.path.getsize(dest) == size:
                return name, "kept"
            part = dest + ".part"
            with urllib.request.urlopen(url, timeout=300) as r, open(part, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if os.path.getsize(part) != size:
                raise OSError(f"short read: {os.path.getsize(part)} != {size}")
            os.replace(part, dest)
            return name, "ok"
        except Exception as e:  # noqa: BLE001 — retry whatever the transport threw
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{name}: {last_err}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", required=True,
                    help="lon_w,lat_s,lon_e,lat_n (e.g. 11.5,47.5,19.5,51.5)")
    ap.add_argument("--out", required=True, help="destination directory")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="print URLs only")
    a = ap.parse_args()

    w, s, e, n = (float(v) for v in a.bbox.split(","))
    tiles = tiles_for_bbox(w, s, e, n)
    if a.dry_run:
        for lat, lon in tiles:
            print(tile_url(lat, lon))
        return 0

    os.makedirs(a.out, exist_ok=True)
    print(f"glo30: {len(tiles)} tiles for bbox {a.bbox} → {a.out}", flush=True)
    failed = 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = [pool.submit(fetch_tile, lat, lon, a.out) for lat, lon in tiles]
        for fut in futures:
            try:
                name, status = fut.result()
                print(f"  {status:5s} {name}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  FAIL  {exc}", flush=True)
    if failed:
        print(f"glo30: {failed} tile(s) failed — rerun resumes", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
