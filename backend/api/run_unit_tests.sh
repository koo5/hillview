#!/bin/bash
# cd to backend (workspace root)
cd "$(dirname "$(readlink -f -- "$0")")/.."

uv sync --frozen --package hillview-api --all-extras

cd api/app
export PYTHONPATH="$(pwd):$(pwd)/../.."

if [ $# -eq 0 ]; then
    uv run pytest tests/unit/ -v
else
    uv run pytest "$@"
fi
