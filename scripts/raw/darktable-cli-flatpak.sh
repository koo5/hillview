#!/bin/sh
# Wrapper that invokes the flatpak darktable-cli as if it were a normal binary,
# then copies lens/camera EXIF from the input raw onto the output image.
# darktable strips fields that Hugin reads (Make, Model, LensModel,
# FocalLength) during export, which makes Hugin prompt for lens parameters.
#
# Point Hugin's RAW converter (Preferences -> RAW converter -> darktable) at
# this file to use the flatpak install instead of the distro package.
#
# Install suggestion (so tools that expect `darktable-cli` on PATH find it):
#   ln -s "$PWD/darktable-cli-flatpak.sh" ~/.local/bin/darktable-cli

# Parse args to locate input raw and output image, and detect whether the
# caller already passed --apply-custom-presets. Everything else (flags,
# --core options, a temp XMP path from Hugin) is forwarded as-is.
#
# darktable-cli supports two input shapes: a raw file (CR2/etc.) or an
# already-developed image (TIFF/JPG/etc., e.g. when re-processing an enfuse
# output through an XMP). For the image-format case the first image-format
# arg is the input and the last is the output; for the raw case the raw is
# the input and the lone image is the output. Track which we're in.
input=""
output=""
has_acp=0
for a in "$@"; do
    case "$a" in
        --apply-custom-presets)
            has_acp=1
            ;;
        *.[Cc][Rr]2|*.[Nn][Ee][Ff]|*.[Aa][Rr][Ww]|*.[Dd][Nn][Gg]|*.[Rr][Ww]2|*.[Rr][Aa][Ff]|*.[Ii][Ii][Qq]|*.[Oo][Rr][Ff]|*.[Pp][Ee][Ff])
            [ -z "$input" ] && input="$a"
            ;;
        *.[Tt][Ii][Ff]|*.[Tt][Ii][Ff][Ff]|*.[Jj][Pp][Gg]|*.[Jj][Pp][Ee][Gg]|*.[Pp][Nn][Gg]|*.[Ee][Xx][Rr])
            if [ -z "$input" ]; then
                input="$a"
            else
                output="$a"
            fi
            ;;
    esac
done

# Default to --apply-custom-presets false so multiple instances don't contend
# on the shared library database (darktable's documented recommendation for
# "multiple instances"). Respect an explicit value if the caller passed one.
if [ "$has_acp" -eq 0 ]; then
    set -- --apply-custom-presets false "$@"
fi

flatpak run --command=darktable-cli org.darktable.Darktable "$@"
rc=$?

if [ "$rc" -eq 0 ] && [ -n "$input" ] && [ -f "$input" ] && [ -n "$output" ] && [ -f "$output" ]; then
    # Copy (almost) everything from the raw. Dimensional / structural tags
    # are intentionally skipped since darktable's output has its own. The
    # FocalPlane* trio is what Hugin needs for HFOV; the rest is useful
    # downstream (GPS, timestamps, lens info).
    exiftool -overwrite_original \
        -TagsFromFile "$input" \
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
        "$output" >/dev/null 2>&1
    # darktable physically applies orientation via its flip module, so force
    # Orientation=1 (normal) to stop viewers and Hugin from rotating pixels
    # again. Separate pass because -TagsFromFile overrides =VALUE assignments,
    # and -n (numeric) because on some TIFFs exiftool mis-PrintConvs "=1".
    exiftool -overwrite_original -n -Orientation=1 "$output" >/dev/null 2>&1
fi

exit "$rc"
