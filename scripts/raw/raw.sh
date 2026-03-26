#!/usr/bin/env bash
DIR="$(dirname "$(readlink -m "$0")")"
exec python3 "$DIR/raw.py" "$@"
