#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")/.."

uv sync --frozen --package hillview-tests

cd tests
export PYTHONPATH="$(pwd)/../api/app:$(pwd)/.."

if [ $# -eq 0 ]; then
    uv run pytest integration/ -v
else
    uv run pytest "$@"
fi
