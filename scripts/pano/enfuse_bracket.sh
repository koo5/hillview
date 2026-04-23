#!/usr/bin/env bash
# Fuse a bracketed exposure stack (same tripod position, varying shutter)
# into a single display-referred TIFF via align_image_stack + enfuse.
#
# - align_image_stack (from hugin-tools) corrects small handheld jitter
#   between frames using control-point-based alignment. Much better than
#   darktable's built-in HDR-DNG merge for handheld brackets.
# - enfuse (from enblend-enfuse) blends via exposure fusion — *not* HDR
#   tone-mapping — so the output is display-ready LDR without any tone
#   curve to fiddle with.
#
# Inputs are TIFFs (typically 16-bit from darktable-cli); produce these
# from CR2 first via scripts/raw/raw_darktable.py or darktable-cli directly.
#
# Usage:
#   enfuse_bracket.sh OUT.tif IN1.tif IN2.tif [IN3.tif ...]

set -euo pipefail

if [ $# -lt 3 ]; then
    echo "usage: $0 OUT.tif IN1.tif IN2.tif [IN3.tif ...]" >&2
    echo "    (needs at least 2 input TIFFs; typically 3 or 5 bracketed frames)" >&2
    exit 2
fi

OUT="$1"
shift

TMPDIR=$(mktemp -d -t enfuse_bracket.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

align_image_stack -a "$TMPDIR/aligned_" "$@"
enfuse --output="$OUT" "$TMPDIR"/aligned_*.tif

echo "wrote $OUT" >&2
