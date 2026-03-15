#!/usr/bin/env fish

set correction $argv[1]
echo "Using correction: $correction"

python3 (dirname (readlink -m (status --current-filename)))/geo_tag_photos.py ~/GeoTrackingDumps $correction --parallel 40 webp/*
