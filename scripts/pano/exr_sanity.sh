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
# Usage:  exr_sanity.sh [--expect linear|srgb|any] [--check-tag] FILE.exr
#
# Without --expect, reads hillview:encoding off the file and treats absence
# as a hard failure (the Hillview worker would reject it).
#
# With --expect linear|srgb, ignores any tag on the file and treats it as
# if it had the named encoding. Use to sanity-check producer output (e.g.
# a darktable export) BEFORE running the tag step, so a downstream failure
# can be blamed on the tagger vs. the producer.
#
# With --expect any, makes no encoding assertion — only the universal
# checks (inf/nan, no value-range bounds) run. Use upstream of producers
# whose output range we don't want to constrain (e.g. enblend, which can
# overshoot above 1.0 from multi-band blending).
#
# With --check-tag (requires --expect linear|srgb), additionally reads the
# file's hillview:encoding tag and fails if it doesn't equal --expect.
# Use post-tag to assert both 'data looks right' AND 'tag was set right'
# in one call — catches a tagger that silently set the wrong value, with
# a clearer error than the range/tag-mismatch SUSPICIOUS verdict.

set -euo pipefail

EXPECT=
CHECK_TAG=
while [ $# -gt 0 ]; do
    case "$1" in
        --expect)  EXPECT="$2"; shift 2 ;;
        --expect=*) EXPECT="${1#*=}"; shift ;;
        --check-tag) CHECK_TAG=1; shift ;;
        --) shift; break ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *)  break ;;
    esac
done

if [ $# -ne 1 ]; then
    echo "usage: $0 [--expect linear|srgb|any] [--check-tag] FILE.exr" >&2
    exit 2
fi

FILE="$1"
SCRIPT_DIR=$(dirname -- "$(readlink -f -- "$0")")

if [ -n "$EXPECT" ]; then
    case "$EXPECT" in
        linear|srgb|any) ENCODING="$EXPECT" ;;
        *) echo "--expect must be 'linear', 'srgb', or 'any'" >&2; exit 2 ;;
    esac
    if [ -n "$CHECK_TAG" ]; then
        if [ "$EXPECT" = "any" ]; then
            echo "--check-tag is meaningless with --expect any" >&2
            exit 2
        fi
        ACTUAL_TAG=$("$SCRIPT_DIR/exr_meta.py" show "$FILE" \
            | awk -F' = ' '/^hillview:encoding/ { print $2; exit }')
        if [ "$ACTUAL_TAG" != "$EXPECT" ]; then
            printf 'file:     %s\n' "$FILE"
            printf 'expected: %s\n' "$EXPECT"
            printf 'actual:   %s\n' "${ACTUAL_TAG:-<missing>}"
            echo   'verdict: TAG MISMATCH — file is tagged differently than expected.'
            echo   '         The tagger (e.g. exr_meta.py set --encoding ...) either'
            echo   '         silently failed or set the wrong value.'
            exit 1
        fi
    fi
else
    if [ -n "$CHECK_TAG" ]; then
        echo "--check-tag requires --expect" >&2
        exit 2
    fi
    ENCODING=$("$SCRIPT_DIR/exr_meta.py" show "$FILE" \
        | awk -F' = ' '/^hillview:encoding/ { print $2; exit }')
fi

MIN=$(LC_ALL=C vips min "$FILE")
MAX=$(LC_ALL=C vips max "$FILE")

printf 'file:     %s\n' "$FILE"
if [ -n "$EXPECT" ]; then
    printf 'encoding: %s (expected, tag not consulted)\n' "$ENCODING"
else
    printf 'encoding: %s\n' "${ENCODING:-<missing>}"
fi
printf 'range:    [%s, %s]\n' "$MIN" "$MAX"

# Universal failure modes — bad regardless of tag.
case "$MIN $MAX" in
    *nan*|*inf*)
        echo 'verdict: BROKEN — pixel values include inf or nan.'
        echo '         A module produced numerically unstable output. On'
        echo '         gigapixel inputs the usual culprits are bilat (local'
        echo '         laplacian mode), hazeremoval, or denoiseprofile.'
        echo '         Disable via xmp_module.py and rerun.'
        exit 1
        ;;
esac

if [ -z "$ENCODING" ]; then
    echo 'verdict: MISSING hillview:encoding — Hillview worker will reject.'
    echo '         tag with: exr_meta.py set FILE --encoding {linear,srgb}'
    exit 1
fi

# 'any' mode: encoding-agnostic, just report the range. Universal failures
# (inf/nan) were already checked above.
if [ "$ENCODING" = "any" ]; then
    echo 'verdict: no encoding assertion (universal checks passed)'
    exit 0
fi

case "$ENCODING" in
    linear)
        # Threshold is generous: tone-mapped panos sit near [0, 1] with a
        # small HDR tail; a pre-tone-map stitch can hit ~20. Past 50 implies
        # the source EXR was written with a non-linear-matrix output profile
        # (we saw max=243 once with sRGB-with-OETF as the colorout profile).
        if awk "BEGIN { exit !($MAX > 50) }"; then
            echo 'verdict: SUSPICIOUS — encoding=linear but max > 50; expected'
            echo '         scene-linear bounded near [0, ~5]. Two likely causes:'
            echo "           - producing tool's output color profile isn't a linear"
            echo '             matrix profile (use linear Rec709/Rec2020 RGB)'
            echo '           - a numerically unstable module on gigapixel input —'
            echo '             bilat (both bilateral-grid and local-laplacian),'
            echo '             hazeremoval, denoiseprofile have all been observed'
            echo '             producing wildly out-of-range values at this scale'
            exit 1
        elif awk "BEGIN { exit !($MAX > 1.5) }"; then
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
