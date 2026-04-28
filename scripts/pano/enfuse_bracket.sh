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
INPUTS=("$@")

TMPDIR=$(mktemp -d -t enfuse_bracket.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

# -t 1: tighten CP reprojection error threshold from default 3px to 1px.
# Moving objects (cars, pedestrians) within a bracket produce CPs that are
# self-consistent across frames but disagree with the stationary majority;
# the tighter threshold drops them before they pull the solve sideways.
align_image_stack -t 1 -a "$TMPDIR/aligned_" "${INPUTS[@]}"
enfuse --output="$OUT" "$TMPDIR"/aligned_*.tif

# enfuse strips EXIF. Without Make/Model/FocalLength the output has no
# focal-length metadata, so pto_gen can't derive HFOV ("No value for
# field of view found"). Copy from the middle bracket — usually the best-
# exposed representative — back onto the fused image.
MIDDLE="${INPUTS[$((${#INPUTS[@]} / 2))]}"
if command -v exiftool >/dev/null 2>&1; then
    # Copy (almost) everything from the middle bracket. Explicitly skips
    # dimensional / structural tags that change with each processing step
    # (ImageWidth/Height, Orientation, etc). The FocalPlane* trio is what
    # Hugin reads to derive sensor width -> HFOV; without them pto_gen errors
    # with "No value for field of view found".
    exiftool -overwrite_original \
        -TagsFromFile "$MIDDLE" \
        -Make -Model -LensModel -LensInfo \
        -FocalLength -FocalLengthIn35mmFilm \
        -FocalPlaneXResolution -FocalPlaneYResolution -FocalPlaneResolutionUnit \
        -DateTimeOriginal -CreateDate -ModifyDate \
        -ISO -ExposureTime -FNumber -ExposureCompensation -ExposureProgram \
        -WhiteBalance -Flash \
        -GPSLatitude -GPSLongitude -GPSAltitude \
        -GPSLatitudeRef -GPSLongitudeRef -GPSAltitudeRef \
        -GPSDateStamp -GPSTimeStamp \
        -Artist -Copyright -UserComment -ImageDescription \
        "$OUT" >/dev/null 2>&1 \
        || echo "warning: exiftool EXIF copy failed on $OUT" >&2
else
    echo "warning: exiftool not on PATH; $OUT has no camera EXIF" >&2
fi

echo "wrote $OUT" >&2
