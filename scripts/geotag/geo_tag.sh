#!/usr/bin/env fish

set script_dir (dirname (readlink -m (status --current-filename)))

uv run --project $script_dir $script_dir/geo_tag_photos.py $argv
