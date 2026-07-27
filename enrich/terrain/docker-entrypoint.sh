#!/bin/sh
# Auto-DSM: when no TERRAIN_DSM_PATH is provided, fill the /dem volume with
# the Copernicus GLO-30 tiles covering TERRAIN_AUTO_DEM_BBOX (one-time; reruns
# only HEAD-check complete tiles) and stitch them into one VRT layer. 30 m
# surface data — plenty for skylines; for the fine ČÚZK near-ring, mount the
# mosaics and set TERRAIN_DSM_PATH/TERRAIN_DTM_PATH — this path steps aside.
set -eu

if [ -z "${TERRAIN_DSM_PATH:-}" ]; then
    bbox="${TERRAIN_AUTO_DEM_BBOX:-11.5,47.5,19.5,51.5}"
    echo "terrain-worker: no TERRAIN_DSM_PATH — auto GLO-30 for bbox $bbox"
    python download_glo30.py --bbox "$bbox" --out /dem/glo30
    # cheap and idempotent, so rebuild every start — a grown bbox just works;
    # -resolution highest reconciles the 50°N tile-width change
    gdalbuildvrt -resolution highest /dem/glo30.vrt /dem/glo30/*.tif
    export TERRAIN_DSM_PATH=/dem/glo30.vrt
    # GLO-30 licence Art. 6(b): derived works must carry this exact notice —
    # the worker stamps it into each render's meta and the UIs display it
    export TERRAIN_ATTRIBUTION="${TERRAIN_ATTRIBUTION:-produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved}"
fi

exec python -m remoulade worker --threads 1
