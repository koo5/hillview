#!/usr/bin/env bash

DIR="$(dirname "$(readlink -m "$0")")"

../geo_tag/pull.sh
exec python3 "$DIR/raw.py" "$@"
