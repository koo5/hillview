#!/usr/bin/env bash
# Report an EXR's hillview:encoding tag, pixel value range, and sanity-check
# whether the range is consistent with the tag.
#
# encoding=linear:    pixels are scene-linear. Bounded panos sit in [0, 1];
#                     true HDR (sun, specular highlights) can exceed 1 and
#                     needs a tone curve (sRGB gamma, filmic, Reinhard)
#                     before scale-and-cast to 8-bit.
# encoding=srgb:      pixels are display-referred (sRGB OETF already
#                     applied), bounded in [0, 1]. Scale-and-cast safe.
#                     See exr_to_webp_pyramid.py for both paths.
# missing:            rejected — silent guesses silently miscolor outputs.
#                     Tag with: exr_meta.py set FILE --encoding {linear,srgb}
#
# Usage:  exr_sanity.sh FILE.exr

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 FILE.exr" >&2
    exit 2
fi

FILE="$1"
SCRIPT_DIR=$(dirname -- "$(readlink -f -- "$0")")

ENCODING=$("$SCRIPT_DIR/exr_meta.py" show "$FILE" \
    | awk -F' = ' '/^hillview:encoding/ { print $2; exit }')

MIN=$(LC_ALL=C vips min "$FILE")
MAX=$(LC_ALL=C vips max "$FILE")

printf 'file:     %s\n' "$FILE"
printf 'encoding: %s\n' "${ENCODING:-<missing>}"
printf 'range:    [%s, %s]\n' "$MIN" "$MAX"

if [ -z "$ENCODING" ]; then
    echo 'verdict: MISSING hillview:encoding — Hillview worker will reject.'
    echo '         tag with: exr_meta.py set FILE --encoding {linear,srgb}'
    exit 1
fi

case "$ENCODING" in
    linear)
        if awk "BEGIN { exit !($MAX > 1.5) }"; then
            echo 'verdict: scene-linear HDR (max > 1.5) — needs tone-mapping for 8-bit display'
        elif awk "BEGIN { exit !($MAX > 1.1) }"; then
            echo 'verdict: scene-linear, slightly above 1.0 — float headroom from blending; OK'
        else
            echo 'verdict: scene-linear, bounded in ~[0, 1] — typical for SDR pano'
        fi
        ;;
    srgb)
        if awk "BEGIN { exit !($MAX > 1.1) }"; then
            echo 'verdict: SUSPICIOUS — encoding=srgb but max > 1.1; should be bounded in [0, 1]'
            exit 1
        elif awk "BEGIN { exit !($MAX < 0.5) }"; then
            echo 'verdict: display-referred but unusually dark (max < 0.5)'
        else
            echo 'verdict: display-referred, ready for scale-and-cast to 8-bit'
        fi
        ;;
    *)
        echo "verdict: UNKNOWN encoding=$ENCODING — only 'linear' and 'srgb' are recognized"
        exit 1
        ;;
esac
