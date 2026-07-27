#!/bin/sh
# Bbox-scoped ČÚZK near-ring build into /dem/cuzk — the containerized twin of
# the manual README flow. DMP 1G (surface → DSM rays) + DMR 5G (bare earth →
# DTM grounding), rasterized at 2 m (pdal), warped to the 10 m EPSG:4326 near
# ring, assembled into one VRT per raster.
#
# Every stage is INCREMENTAL: downloads skip complete files, rasterize/warp
# skip existing outputs, the cheap VRT rebuild picks up whatever is present.
# So the tree only ever grows — a bigger bbox later (or the whole-republic
# overnight prefetch: same command, CZ-wide bbox, `docker compose run`) just
# adds sheets. Disk note: zips + laz + 2 m rasters + 10 m warps all stay in
# the volume (that's the resumability), roughly 3-4× the raw download.
set -eu

bbox="$1"
base=/dem/cuzk
echo "auto_cuzk: ČÚZK near ring for bbox $bbox → $base (incremental)"

python download_cuzk.py fetch --dataset dmp1g --out "$base/dl/dmp1g" --bbox "$bbox" --unzip
python download_cuzk.py fetch --dataset dmr5g --out "$base/dl/dmr5g" --bbox "$bbox" --unzip

if ! ls "$base"/dl/dmp1g/laz/*.la[sz] >/dev/null 2>&1; then
    echo "auto_cuzk: no sheets for bbox $bbox (outside CZ coverage?) — nothing to build"
    exit 0
fi

python build_mosaic.py rasterize --laz-dir "$base/dl/dmp1g/laz" --out-dir "$base/rast/dsm" --res-m 2 --kind dsm
python build_mosaic.py rasterize --laz-dir "$base/dl/dmr5g/laz" --out-dir "$base/rast/dtm" --res-m 2 --kind dtm
python build_mosaic.py warp --in-dir "$base/rast/dsm" --out-dir "$base/warp/dsm10" --res-m 10 --s-srs "EPSG:5514+8357"
python build_mosaic.py warp --in-dir "$base/rast/dtm" --out-dir "$base/warp/dtm10" --res-m 10 --s-srs "EPSG:5514+8357"
# 2 m near ring: native-ish lidar sharpness for the first few km — nearby
# trees/buildings render as shapes instead of interpolated 10 m slabs
python build_mosaic.py warp --in-dir "$base/rast/dsm" --out-dir "$base/warp/dsm2" --res-m 2 --s-srs "EPSG:5514+8357"
python build_mosaic.py vrt --in-dirs "$base/warp/dsm2" --out "$base/dsm2.vrt"
python build_mosaic.py vrt --in-dirs "$base/warp/dsm10" --out "$base/dsm10.vrt"
python build_mosaic.py vrt --in-dirs "$base/warp/dtm10" --out "$base/dtm10.vrt"
echo "auto_cuzk: done — $base/dsm2.vrt + dsm10.vrt + dtm10.vrt"
