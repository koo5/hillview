#!/usr/bin/env bash
# Report an EXR's pixel value range and classify it as display-referred or
# scene-linear. Panoramas from this directory's pipeline should be
# display-referred (sRGB-encoded floats in [0, 1]) because darktable's
# default output profile is sRGB.
#
# - Display-referred: convert to 8-bit with plain scale-and-cast
#   (multiply by 255, cast uchar, no gamma). See exr_to_webp_pyramid.py.
# - Scene-linear: values may be unbounded above 1.0 (bright highlights,
#   sun, specular reflections). Scale-and-cast will clip; use a tone
#   curve (sRGB gamma, filmic, Reinhard) before casting.
#
# Usage:  exr_sanity.sh FILE.exr

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 FILE.exr" >&2
    exit 2
fi

MIN=$(LC_ALL=C vips min "$1")
MAX=$(LC_ALL=C vips max "$1")

printf 'file:   %s\n' "$1"
printf 'range:  [%s, %s]\n' "$MIN" "$MAX"

if awk "BEGIN { exit !($MAX > 1.1) }"; then
    echo 'verdict: SCENE-LINEAR (max > 1.1) — tone-map before casting to 8-bit'
    exit 1
elif awk "BEGIN { exit !($MAX < 0.5) }"; then
    echo 'verdict: display-referred but unusually dark (max < 0.5) — image may look too dim'
else
    echo 'verdict: display-referred, safe for scale-and-cast'
fi
