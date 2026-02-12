#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")/.."

uv sync --frozen --package hillview-worker --all-extras

cd worker
export PYTHONPATH="$(pwd):$(pwd)/.."

if [ $# -eq 0 ]; then
    uv run pytest tests/unit/ -v
else
    uv run pytest "$@"
fi
