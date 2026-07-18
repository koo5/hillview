#!/usr/bin/env bash
# Run the MASt3R matcher worker under a systemd transient SERVICE with a hard
# memory ceiling — the "braces" of the OOM protection (the ram_gate in worker.py
# is the belt). MemoryHigh throttles/reclaims first; MemoryMax is the kernel
# kill line — and it kills ONLY this unit, never the box. Restart=on-failure
# resurrects the worker after an OOM kill; the unacked RabbitMQ message gets
# redelivered (actor max_retries=1 caps poison-job loops).
#
#   ./run_worker.sh            # start (or restart) the unit
#   journalctl --user -u enrich-matcher -f     # logs
#   systemctl --user stop enrich-matcher       # stop
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$HERE/../../scripts/enrich/.venv/bin/python"
MEM_HIGH="${MATCHER_MEM_HIGH:-8G}"
MEM_MAX="${MATCHER_MEM_MAX:-10G}"

systemctl --user stop enrich-matcher 2>/dev/null || true
systemctl --user reset-failed enrich-matcher 2>/dev/null || true

systemd-run --user --unit=enrich-matcher \
  --working-directory="$HERE" \
  -p MemoryHigh="$MEM_HIGH" \
  -p MemoryMax="$MEM_MAX" \
  -p MemorySwapMax=0 \
  -p Restart=on-failure \
  -p RestartSec=30 \
  --setenv=RABBITMQ_URL="${RABBITMQ_URL:-enrich:enrich@127.0.0.1:5672}" \
  --setenv=MATCHER_REQUIRED_GB="${MATCHER_REQUIRED_GB:-6}" \
  "$VENV_PY" -m remoulade worker --threads 1

echo "enrich-matcher unit started (MemoryHigh=$MEM_HIGH, MemoryMax=$MEM_MAX)"
systemctl --user status enrich-matcher --no-pager | head -6
