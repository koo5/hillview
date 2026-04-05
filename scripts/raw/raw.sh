#!/usr/bin/env bash

DIR="$(dirname "$(readlink -m "$0")")"

$DIR/../geotag/pull.sh
exec python3 "$DIR/raw.py" "$@"
