#!/usr/bin/env bash
# Run the terrain render worker under a systemd transient SERVICE with a hard
# memory ceiling — same belt-and-braces shape as matcher/run_worker.sh (the
# ram_gate in worker.py is the belt). Rendering is much lighter than MASt3R:
# the big allocation is the windowed DEM read (a 100 km radius of 30 m cells
# is ~180 MB; a 10 m composite ~1.6 GB), hence the smaller defaults.
#
#   ./run_worker.sh            # start (or restart) the unit
#   journalctl --user -u enrich-terrain -f     # logs
#   systemctl --user stop enrich-terrain       # stop
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${TERRAIN_PYTHON:-$HERE/../../scripts/enrich/.venv/bin/python}"
MEM_HIGH="${TERRAIN_MEM_HIGH:-3G}"
MEM_MAX="${TERRAIN_MEM_MAX:-4G}"

systemctl --user stop enrich-terrain 2>/dev/null || true
systemctl --user reset-failed enrich-terrain 2>/dev/null || true

systemd-run --user --unit=enrich-terrain \
  --working-directory="$HERE" \
  -p MemoryHigh="$MEM_HIGH" \
  -p MemoryMax="$MEM_MAX" \
  -p MemorySwapMax=0 \
  -p Restart=on-failure \
  -p RestartSec=30 \
  --setenv=RABBITMQ_URL="${RABBITMQ_URL:-enrich:enrich@127.0.0.1:5672}" \
  --setenv=TERRAIN_CALLBACK_URL="${TERRAIN_CALLBACK_URL:-http://127.0.0.1:8070/api/terrain/result}" \
  --setenv=ENRICH_WORKER_TOKEN="${ENRICH_WORKER_TOKEN:-dev-worker-token}" \
  --setenv=TERRAIN_DSM_PATH="${TERRAIN_DSM_PATH:-${TERRAIN_DEM_PATH:-}}" \
  --setenv=TERRAIN_DTM_PATH="${TERRAIN_DTM_PATH:-}" \
  --setenv=TERRAIN_GEOID_OFFSET_M="${TERRAIN_GEOID_OFFSET_M:-44.5}" \
  --setenv=TERRAIN_REQUIRED_GB="${TERRAIN_REQUIRED_GB:-2}" \
  "$VENV_PY" -m remoulade worker --threads 1

echo "enrich-terrain unit started (MemoryHigh=$MEM_HIGH, MemoryMax=$MEM_MAX)"
systemctl --user status enrich-terrain --no-pager | head -6
