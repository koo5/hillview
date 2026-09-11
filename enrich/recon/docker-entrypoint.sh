#!/bin/sh
# Bring up the recon worker on a rented GPU box, and refuse to start in any state that
# would quietly waste rent: no GPU, no kernel, no checkpoint, a checkpoint that is not the
# one we meant to run.
#
# Every check here is cheap and happens once per instance. The expensive mistake is the
# other kind — a box that looks healthy in the bench, bills by the second, and is running
# the slow path or the wrong weights.
set -eu

log() { echo "recon-worker: $*"; }

RUNS_DIR="${RECON_RUNS_DIR:-/runs/bench}"
CKPT="${MAST3R_CKPT:-/runs/mast3r.pth}"
mkdir -p "$RUNS_DIR" "${RECON_SHARED_CACHE:-/runs/shared_cache}" \
         "${HV_SEMANTIC_CACHE:-/runs/semantic_cache}"

# --- the card ---------------------------------------------------------------
if [ "${RECON_DEVICE:-auto}" != "cpu" ]; then
    python -c "
import sys, torch
if not torch.cuda.is_available():
    sys.exit('no CUDA device visible to torch — rent with a GPU, or set RECON_DEVICE=cpu')
free, total = torch.cuda.mem_get_info()
print(f'recon-worker: {torch.cuda.get_device_name(0)}, {total / 2**30:.0f} GiB '
      f'({free / 2**30:.0f} free), torch {torch.__version__}')
"
    # The CUDA RoPE2D kernel: dust3r only warns and falls back, so this is the difference
    # between minutes and hours with no error to notice.
    PYTHONPATH="${MAST3R_REPO:-/opt/mast3r}/dust3r/croco" python -c "
from models.curope import cuRoPE2D
print('recon-worker: curope OK')
" || { log "FATAL: the CUDA RoPE2D kernel did not load — this image would run the slow path"; exit 1; }
fi

# --- the weights ------------------------------------------------------------
# Deliberately not baked into the image: torch.load runs what is inside a checkpoint, so
# it comes from a host you control, over the tunnel or the VPS route, checksum-verified.
if [ ! -f "$CKPT" ]; then
    [ -n "${RECON_CKPT_URL:-}" ] || { log "FATAL: no $CKPT and no RECON_CKPT_URL to fetch it from"; exit 1; }
    log "fetching the MASt3R checkpoint (2.6 GiB) from ${RECON_CKPT_URL%%\?*}"
    curl -fL --retry 5 --retry-delay 5 -o "$CKPT.part" "$RECON_CKPT_URL"
    mv "$CKPT.part" "$CKPT"
fi
if [ -n "${RECON_CKPT_SHA256:-}" ]; then
    got="$(sha256sum "$CKPT" | cut -d' ' -f1)"
    [ "$got" = "$RECON_CKPT_SHA256" ] || {
        log "FATAL: checkpoint checksum mismatch"; log "  expected $RECON_CKPT_SHA256"; log "  got      $got"; exit 1; }
    log "checkpoint verified"
else
    log "WARNING: RECON_CKPT_SHA256 unset — running an unverified checkpoint"
fi

# --- reachability, before the queue hands us a job we cannot report on -------
python - <<'PY' || exit 1
import os, sys, urllib.parse
url = os.getenv("RECON_CALLBACK_URL", "http://127.0.0.1:8070/api/recon/result")
amqp = os.getenv("RABBITMQ_URL", "enrich:enrich@127.0.0.1:5672")
import socket
for label, hostport in (("callback", urllib.parse.urlparse(url).netloc),
                        ("broker", amqp.rsplit("@", 1)[-1])):
    host, _, port = hostport.partition(":")
    port = int(port or (443 if url.startswith("https") and label == "callback" else 80))
    try:
        socket.create_connection((host, port), timeout=10).close()
        print(f"recon-worker: {label} {host}:{port} reachable")
    except OSError as e:
        sys.exit(f"recon-worker: FATAL: {label} {host}:{port} unreachable ({e}) — "
                 "is the tunnel up?")
PY

# OpenMP threads: the non-solve stages (download, dense extraction, PLY writing) are the
# CPU-side work here, and a rented box's core count is whatever the host gave us.
THREADS="${RECON_THREADS:-$(nproc)}"
export OMP_NUM_THREADS="$THREADS" MKL_NUM_THREADS="$THREADS" TORCH_NUM_THREADS="$THREADS"
log "starting worker with $THREADS threads, device ${RECON_DEVICE:-auto}"

# No systemd here, so no MemoryHigh/MemoryMax braces — worker.py's ram_gate is the belt,
# and a container OOM kills only this container.
cd /app/enrich/recon
exec python -m remoulade worker --threads 1
