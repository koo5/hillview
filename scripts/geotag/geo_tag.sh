#!/usr/bin/env fish

set script_dir (dirname (readlink -m (status --current-filename)))

if test (count $argv) -ge 1
    set correction $argv[1]
    echo "Using provided correction: $correction" >&2
else
    echo "No correction provided, scanning QR calibration photos..." >&2
    set correction (uv run $script_dir/qr_time_correction.py webp/*)
    if test $status -ne 0
        echo "Failed to obtain correction from QR photos" >&2
        exit 1
    end
    echo "Auto-detected correction: $correction" >&2
end

uv run $script_dir/geo_tag_photos.py ~/GeoTrackingDumps $correction --parallel 40 webp/*
