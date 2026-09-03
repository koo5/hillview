#!/bin/bash
# Unit tests for the panoramax federation service (no DB needed).
# Mirrors backend/api/run_unit_tests.sh.
set -e

cd "$(dirname "$(readlink -f -- "$0")")/.."      # backend/

uv sync --quiet --frozen --package hillview-panoramax --all-extras

cd panoramax/app
export PYTHONPATH="$(pwd):$(pwd)/../.."

if [ $# -eq 0 ]; then
	uv run --quiet pytest tests/unit/ -v
else
	uv run --quiet pytest "$@"
fi
