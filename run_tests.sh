#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

# Warn (never block) if a built container is older than the working tree it was
# built from — tests run against the deployed stack, so stale images = stale code.
# Warn-only by design: it exits 0 here. To make staleness a hard failure, add
# --strict and move it into the && chain below.
python3 scripts/check_container_freshness.py

./backend/run_tests.sh && ./frontend/run_tests.sh
