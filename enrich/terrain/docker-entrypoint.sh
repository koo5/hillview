#!/bin/sh
# Auto-DSM: when no TERRAIN_DSM_PATH is provided, fill the /dem volume with
# the Copernicus GLO-30 tiles covering TERRAIN_AUTO_DEM_BBOX (one-time; reruns
# only HEAD-check complete tiles) and stitch them into one VRT layer. 30 m
# surface data — plenty for skylines; for the fine ČÚZK near-ring, mount the
# mosaics and set TERRAIN_DSM_PATH/TERRAIN_DTM_PATH — this path steps aside.
set -eu

auto_dsm=""
if [ -z "${TERRAIN_DSM_PATH:-}" ]; then
    auto_dsm=1
    bbox="${TERRAIN_AUTO_DEM_BBOX:-11.5,47.5,19.5,51.5}"
    echo "terrain-worker: no TERRAIN_DSM_PATH — auto GLO-30 for bbox $bbox"
    python download_glo30.py --bbox "$bbox" --out /dem/glo30
    # cheap and idempotent, so rebuild every start — a grown bbox just works;
    # -resolution highest reconciles the 50°N tile-width change
    gdalbuildvrt -resolution highest /dem/glo30.vrt /dem/glo30/*.tif
    export TERRAIN_DSM_PATH=/dem/glo30.vrt
    # on-demand worldwide coverage: the worker fetches missing tiles for any
    # render window and refreshes the VRT — the bbox above is just a warm
    # cache that spares the first render in a fresh area the download wait
    export TERRAIN_GLO30_TILES_DIR=/dem/glo30
    export TERRAIN_GLO30_VRT=/dem/glo30.vrt
    # GLO-30 licence Art. 6(b): derived works must carry this exact notice —
    # the worker stamps it into each render's meta and the UIs display it
    export TERRAIN_ATTRIBUTION="${TERRAIN_ATTRIBUTION:-produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved}"
    # the same mosaic as an explicitly selectable stack (dsm_stack=glo30)
    export TERRAIN_DSM_PATH_GLO30="${TERRAIN_DSM_PATH_GLO30:-$TERRAIN_DSM_PATH}"
    export TERRAIN_ATTRIBUTION_GLO30="${TERRAIN_ATTRIBUTION_GLO30:-$TERRAIN_ATTRIBUTION}"
fi

# Optional ČÚZK near ring (dsm_stack=cuzk): bbox-scoped download + pdal
# rasterize + warp + vrt into the volume. Heavy on first build (LAZ point
# clouds), incremental after — a grown bbox only adds sheets. The stack is a
# COMPOSITE: fine ČÚZK capped at 15 km (beyond that a 1 m cell subtends an
# eighth of a pixel), whatever the default DSM is (auto GLO-30) beyond and
# outside the bbox — CompositeDem first-finite-wins covers the seams.
if [ -n "${TERRAIN_AUTO_CUZK_BBOX:-}" ] && [ -z "${TERRAIN_DSM_PATH_CUZK:-}" ]; then
    sh auto_cuzk.sh "$TERRAIN_AUTO_CUZK_BBOX"
    if [ -f /dem/cuzk/dsm10.vrt ]; then
        # rings finest-first: 2 m to 4 km (a 4 km window read at 2 m is
        # ~64 MB — affordable; the ring is what keeps NEAR objects shaped),
        # 10 m to 15 km, the default DSM beyond
        near=""
        [ -f /dem/cuzk/dsm2.vrt ] && near="/dem/cuzk/dsm2.vrt@4000:"
        export TERRAIN_DSM_PATH_CUZK="${near}/dem/cuzk/dsm10.vrt@15000${TERRAIN_DSM_PATH:+:$TERRAIN_DSM_PATH}"
        # DTM also tails into the default DSM: outside ČÚZK coverage the eye
        # grounds on GLO-30 (surface — same as glo30-only renders) instead of
        # failing with "viewpoint outside the DEM"
        export TERRAIN_DTM_PATH_CUZK="${TERRAIN_DTM_PATH_CUZK:-/dem/cuzk/dtm10.vrt${TERRAIN_DSM_PATH:+:$TERRAIN_DSM_PATH}}"
        # a default/cuzk render at a viewpoint OUTSIDE the built rings first
        # extends them on demand (worker runs auto_cuzk.sh around the point —
        # incremental, ±TERRAIN_AUTO_CUZK_RADIUS_M, lock-serialized); =0 to
        # disable and just fall through to GLO-30 there
        export TERRAIN_AUTO_CUZK_FETCH="${TERRAIN_AUTO_CUZK_FETCH:-1}"
        # composite embeds the far-ring DSM → both credits ride the renders
        export TERRAIN_ATTRIBUTION_CUZK="${TERRAIN_ATTRIBUTION_CUZK:-© ČÚZK · ${TERRAIN_ATTRIBUTION:-}}"
        # When the default stack was auto-filled (not user-configured),
        # promote the composite to BE the default: "auto" should mean "best
        # available" — nobody should have to pick a source for normal
        # renders. glo30 stays selectable for explicit A/B comparison.
        if [ -n "$auto_dsm" ]; then
            export TERRAIN_DSM_PATH="$TERRAIN_DSM_PATH_CUZK"
            export TERRAIN_DTM_PATH="${TERRAIN_DTM_PATH:-$TERRAIN_DTM_PATH_CUZK}"
            export TERRAIN_ATTRIBUTION="$TERRAIN_ATTRIBUTION_CUZK"
        fi
    fi
fi

exec python -m remoulade worker --threads 1
