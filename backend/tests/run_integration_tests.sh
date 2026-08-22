#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")/.."

export PYTHONUNBUFFERED=1

# Dev origins (worker, pics) are served by Caddy with a `tls internal` cert that
# Python's CA bundle does not trust. Opt these TESTS out of verification; the
# prod CLI on the same code path (backend/debug.sh) never sets this.
export HILLVIEW_INSECURE_TLS=1

uv sync --quiet --frozen --package hillview-tests

cd tests
export PYTHONPATH="$(pwd)/../api/app:$(pwd)/.."

if [ $# -eq 0 ]; then
    uv run --quiet pytest integration/ -v
else
    uv run --quiet pytest "$@"
fi
