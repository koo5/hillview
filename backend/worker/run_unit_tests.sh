#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")/.."

if ! ldconfig -p 2>/dev/null | grep -q libvips; then
    echo "libvips not found, installing libvips-dev..."
    sudo apt-get install -y -qq libvips-dev
fi

uv sync --quiet --frozen --package hillview-worker --all-extras

cd worker
export PYTHONPATH="$(pwd):$(pwd)/.."

if [ $# -eq 0 ]; then
    uv run --quiet pytest tests/unit/ -v
else
    uv run --quiet pytest "$@"
fi
