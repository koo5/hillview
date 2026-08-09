#!/usr/bin/env python3
"""Build the DSM/DTM mosaics the terrain worker reads (TERRAIN_DSM_PATH /
TERRAIN_DTM_PATH). Thin, inspectable wrapper over pdal + gdal CLI — every
subcommand prints exactly what it runs, and --dry-run prints without running.

Typical ČÚZK + Copernicus flow (open data, CC BY 4.0):

  # 1) rasterize downloaded LAZ sheets (S-JTSK/Bpv stays as-is here)
  #    DMP 1G (surface → DSM, ridge-preserving max) at 2 m:
  ./build_mosaic.py rasterize --laz-dir dl/dmp1g --out-dir rast/dsm --res-m 2 --kind dsm
  #    DMR 5G (bare earth → DTM, smooth idw):
  ./build_mosaic.py rasterize --laz-dir dl/dmr5g --out-dir rast/dtm --res-m 2 --kind dtm

  # 2) warp to the worker's north-up EPSG:4326 grid, one dir per resolution ring
  ./build_mosaic.py warp --in-dir rast/dsm --out-dir warp/dsm10 --res-m 10 --s-srs "EPSG:5514+8357"
  ./build_mosaic.py warp --in-dir rast/dsm --out-dir warp/dsm30 --res-m 30 --s-srs "EPSG:5514+8357" --resampling max
  ./build_mosaic.py warp --in-dir dl/glo30 --out-dir warp/glo30 --res-m 30

  # 3) one VRT per ring/source (each becomes one TERRAIN_DSM_PATH layer)
  ./build_mosaic.py vrt --in-dirs warp/dsm10 --out mosaic/dsm10.vrt
  ./build_mosaic.py vrt --in-dirs warp/dsm30 warp/glo30 --out mosaic/dsm_far.vrt --cog

  # → export TERRAIN_DSM_PATH="mosaic/dsm10.vrt@15000:mosaic/dsm_far.vrt"
  #   export TERRAIN_DTM_PATH="mosaic/dtm10.vrt@15000"

Vertical datum note: Bpv (orthometric) heights pass through untouched — the
renderer only compares heights against each other, so a CONSISTENT vertical
datum is what matters. GLO-30 is EGM2008-referenced, close enough to Bpv for
far-field skylines (decimetres). GPS-altitude datum handling is the worker's
job (renderer.resolve_eye_elevation), not the mosaic's.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

M_PER_DEG_LAT = 111_320.0


# ---------------------------------------------------------------------------
# command construction (pure — unit-testable without pdal/gdal installed)
# ---------------------------------------------------------------------------

def pdal_pipeline(laz: Path, out_tif: Path, res_m: float, kind: str) -> dict:
    """DSM: per-cell max preserves the ridge/canopy line the skyline needs.
    DTM: idw smooths the (already ground-classified) DMR 5G points.
    window_size fills small gaps from neighbouring cells."""
    writer = {
        "type": "writers.gdal",
        "filename": str(out_tif),
        "resolution": res_m,
        "output_type": "max" if kind == "dsm" else "idw",
        "window_size": 3,
        "gdaldriver": "GTiff",
        "gdalopts": "COMPRESS=DEFLATE,PREDICTOR=2,TILED=YES",
        "data_type": "float32",
        "nodata": -9999,
    }
    return {"pipeline": [{"type": "readers.las", "filename": str(laz)}, writer]}

def rasterize_cmd(pipeline_json: Path) -> list[str]:
    return ["pdal", "pipeline", str(pipeline_json)]

def warp_cmd(src: Path, dst: Path, res_m: float, mid_lat: float,
             s_srs: str | None, resampling: str) -> list[str]:
    """-tr in target degrees: metres/deg differs per axis at mid_lat, so the
    4326 grid keeps ~square metric cells there. 'max' resampling on the far
    ring keeps narrow ridges alive through downsampling (aliasing refinement)."""
    dlat = res_m / M_PER_DEG_LAT
    dlon = res_m / (M_PER_DEG_LAT * max(0.1, math.cos(math.radians(mid_lat))))
    cmd = ["gdalwarp", "-t_srs", "EPSG:4326", "-tr", f"{dlon:.10f}", f"{dlat:.10f}",
           "-r", resampling, "-dstnodata", "-9999",
           "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=2", "-co", "TILED=YES",
           "-overwrite"]
    if s_srs:
        cmd += ["-s_srs", s_srs]     # e.g. "EPSG:5514+8357" (S-JTSK + Bpv)
    return cmd + [str(src), str(dst)]

def vrt_cmd(inputs: list[Path], out: Path) -> list[str]:
    return ["gdalbuildvrt", "-resolution", "highest", "-vrtnodata", "-9999",
            str(out)] + [str(p) for p in inputs]

def cog_cmd(vrt: Path, out: Path) -> list[str]:
    return ["gdal_translate", "-of", "COG", "-co", "COMPRESS=DEFLATE",
            "-co", "BIGTIFF=IF_SAFER", str(vrt), str(out)]


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------

def run(cmd: list[str], dry_run: bool) -> None:
    print("  $", " ".join(cmd), flush=True)
    if dry_run:
        return
    if shutil.which(cmd[0]) is None:
        sys.exit(f"{cmd[0]} not found — install pdal / gdal-bin")
    subprocess.run(cmd, check=True)

def rasters_in(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if p.suffix.lower() in {".tif", ".tiff"})


def cmd_rasterize(a: argparse.Namespace) -> None:
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for laz in sorted(a.laz_dir.glob("*.la[sz]")):
        out = a.out_dir / f"{laz.stem}.tif"
        if out.exists() and not a.force:
            print(f"  skip (exists): {out}")
            continue
        pj = a.out_dir / f"{laz.stem}.pipeline.json"
        pj.write_text(json.dumps(pdal_pipeline(laz, out, a.res_m, a.kind), indent=2))
        run(rasterize_cmd(pj), a.dry_run)

def cmd_warp(a: argparse.Namespace) -> None:
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for src in rasters_in(a.in_dir):
        dst = a.out_dir / src.name
        if dst.exists() and not a.force:
            print(f"  skip (exists): {dst}")
            continue
        run(warp_cmd(src, dst, a.res_m, a.mid_lat, a.s_srs, a.resampling), a.dry_run)

def cmd_vrt(a: argparse.Namespace) -> None:
    a.out.parent.mkdir(parents=True, exist_ok=True)
    inputs = [p for d in a.in_dirs for p in rasters_in(d)]
    if not inputs and not a.dry_run:
        sys.exit(f"no rasters under {a.in_dirs}")
    run(vrt_cmd(inputs, a.out), a.dry_run)
    if a.cog:
        run(cog_cmd(a.out, a.out.with_suffix(".tif")), a.dry_run)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rasterize", help="LAZ sheets → GeoTIFF (pdal)")
    r.add_argument("--laz-dir", type=Path, required=True)
    r.add_argument("--out-dir", type=Path, required=True)
    r.add_argument("--res-m", type=float, default=2.0)
    r.add_argument("--kind", choices=["dsm", "dtm"], required=True)

    w = sub.add_parser("warp", help="→ north-up EPSG:4326 at a ring resolution")
    w.add_argument("--in-dir", type=Path, required=True)
    w.add_argument("--out-dir", type=Path, required=True)
    w.add_argument("--res-m", type=float, required=True)
    w.add_argument("--mid-lat", type=float, default=49.8, help="CZ centroid-ish")
    w.add_argument("--s-srs", default=None,
                   help='override source SRS, e.g. "EPSG:5514+8357" for S-JTSK+Bpv')
    w.add_argument("--resampling", default="bilinear",
                   help="bilinear near ring; max for downsampled far rings")

    v = sub.add_parser("vrt", help="assemble one worker layer")
    v.add_argument("--in-dirs", type=Path, nargs="+", required=True)
    v.add_argument("--out", type=Path, required=True)
    v.add_argument("--cog", action="store_true", help="also bake a COG")

    for p in (r, w, v):
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--force", action="store_true", help="overwrite existing outputs")

    a = ap.parse_args(argv)
    {"rasterize": cmd_rasterize, "warp": cmd_warp, "vrt": cmd_vrt}[a.cmd](a)


if __name__ == "__main__":
    main()
