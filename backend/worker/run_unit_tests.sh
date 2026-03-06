#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")/.."

uv sync --quiet --frozen --package hillview-worker --all-extras

cd worker
export PYTHONPATH="$(pwd):$(pwd)/.."

if [ $# -eq 0 ]; then
    uv run --quiet pytest tests/unit/ -v
else
    uv run --quiet pytest "$@"
fi
