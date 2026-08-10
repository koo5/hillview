#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

# Say which host profile is live and what the suite will actually hit, and warn
# when that origin is plain HTTP/1.1 — the connection-cap flake class is active
# there and does not name itself in the failures it causes.
python3 scripts/set_host.py

# Warn (never block) if a built container is older than the working tree it was
# built from — tests run against the deployed stack, so stale images = stale code.
# Warn-only by design: it exits 0 here. To make staleness a hard failure, add
# --strict and move it into the && chain below.
python3 scripts/check_container_freshness.py

./backend/run_tests.sh && ./frontend/run_tests.sh
