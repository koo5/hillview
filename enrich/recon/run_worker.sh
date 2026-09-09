#!/usr/bin/env bash
# Run the recon worker under a systemd transient SERVICE with a hard memory ceiling —
# same belt-and-braces shape as matcher/run_worker.sh and terrain/run_worker.sh (the
# ram_gate in worker.py is the belt, this unit is the braces).
#
# Sized larger than either: MASt3R-SfM holds every pair's correspondences plus the
# optimizer state, and it is the heaviest thing in the stack. Measured ~3.4 GB resident
# re-solving the 48-frame walk_dense from cache; a fresh dense run of that size is more,
# since the forward passes and dense extraction run too. Its own queue and unit mean a
# runaway reconstruction kills only itself, never the matcher or the box.
#
#   ./run_worker.sh                              # start (or restart) the unit
#   journalctl --user -u enrich-recon -f         # logs
#   systemctl --user stop enrich-recon           # stop
#   RECON_UNIT=enrich-recon-2 ./run_worker.sh    # a second worker on the same queue
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${RECON_PYTHON:-$HERE/../../scripts/enrich/.venv/bin/python}"
MEM_HIGH="${RECON_MEM_HIGH:-12G}"
MEM_MAX="${RECON_MEM_MAX:-16G}"
# A second worker on the same queue is a supported thing when the box has the headroom --
# the jobs are hours long and independent. Each unit carries its own ceiling, so N workers
# means N x MEM_MAX worst case: check `free` before raising N.
#   RECON_UNIT=enrich-recon-2 RECON_MEM_MAX=10G RECON_THREADS=8 ./run_worker.sh   (and 8 on the first)
UNIT="${RECON_UNIT:-enrich-recon}"
# Threads per worker. MEASURED 2026-09-09: two workers each left at torch's default
# (one OpenMP thread per core) ran at 140-170 s per pair against 17 s for one worker
# alone -- a ten-fold slowdown, not the two-fold the core split predicts, because
# OpenMP barriers spin when 32 threads share 16 cores. Two workers only make sense
# with THREADS set to a share of nproc each; the default leaves one worker the box.
THREADS="${RECON_THREADS:-$(nproc)}"

if [ ! -x "$VENV_PY" ]; then
	echo "error: no python at $VENV_PY (set RECON_PYTHON)" >&2
	exit 1
fi

systemctl --user stop "$UNIT" 2>/dev/null || true
systemctl --user reset-failed "$UNIT" 2>/dev/null || true

# Restart=on-failure + max_retries=0 on the actor: a killed reconstruction is NOT retried
# automatically. A 50-minute job that died on memory pressure would just die again, and
# the run row already carries the error for the bench to show.
systemd-run --user --unit="$UNIT" \
  --working-directory="$HERE" \
  -p MemoryHigh="$MEM_HIGH" \
  -p MemoryMax="$MEM_MAX" \
  -p MemorySwapMax=0 \
  -p Restart=on-failure \
  -p RestartSec=30 \
  --setenv=RABBITMQ_URL="${RABBITMQ_URL:-enrich:enrich@127.0.0.1:5672}" \
  --setenv=RECON_CALLBACK_URL="${RECON_CALLBACK_URL:-http://127.0.0.1:8070/api/recon/result}" \
  --setenv=ENRICH_WORKER_TOKEN="${ENRICH_WORKER_TOKEN:-dev-worker-token}" \
  --setenv=RECON_RUNS_DIR="${RECON_RUNS_DIR:-$HERE/../../scripts/enrich/runs/bench}" \
  --setenv=RECON_REQUIRED_GB="${RECON_REQUIRED_GB:-8}" \
  --setenv=RECON_PROGRESS_EVERY_S="${RECON_PROGRESS_EVERY_S:-30}" \
  --setenv=OMP_NUM_THREADS="$THREADS" \
  --setenv=MKL_NUM_THREADS="$THREADS" \
  --setenv=TORCH_NUM_THREADS="$THREADS" \
  ${MAST3R_REPO:+--setenv=MAST3R_REPO="$MAST3R_REPO"} \
  ${MAST3R_CKPT:+--setenv=MAST3R_CKPT="$MAST3R_CKPT"} \
  "$VENV_PY" -m remoulade worker --threads 1

echo "$UNIT started (MemoryHigh=$MEM_HIGH, MemoryMax=$MEM_MAX, threads=$THREADS)"
systemctl --user status "$UNIT" --no-pager | head -6
