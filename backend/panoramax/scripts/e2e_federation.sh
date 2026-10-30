#!/bin/bash
# Bootstrap only. All assertions, including --heavy, live in e2e_federation.py.
# The same suite runs against either a local collector or --catalog-ssh HOST.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f -- "$0")")/../../.." && pwd)"
META_CATALOG="${META_CATALOG:-/home/koom/repos/panoramax/server/meta-catalog/0/meta-catalog}"
WORK_DIR="${WORK_DIR:-${TMPDIR:-/tmp}/panoramax-e2e}"
CATALOG_SSH="${CATALOG_SSH:-}"
CATALOG_HARVESTER="${CATALOG_HARVESTER:-}"
CATALOG_CA_BUNDLE="${CATALOG_CA_BUNDLE:-}"
CATALOG_DB="${CATALOG_DB:-postgresql://username:password@localhost:5439/panoramax}"
INSTANCE_NAME="${INSTANCE_NAME:-hillview-e2e}"
KEEP_UP=0
REUSE_STACK=0
DOWN=0
RUN_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --catalog-ssh) CATALOG_SSH="$2"; shift ;;
        --harvester) CATALOG_HARVESTER="$2"; shift ;;
        --ca-bundle) CATALOG_CA_BUNDLE="$2"; shift ;;
        --keep-up) KEEP_UP=1 ;;
        --reuse-stack) REUSE_STACK=1 ;;
        --heavy|--keep-load|--cleanup-load) RUN_ARGS+=("$1") ;;
        --no-seed) RUN_ARGS+=(--heavy --reuse-load) ;;
        --down) DOWN=1 ;;
        --help|-h)
            cat <<'HELP'
Usage: e2e_federation.sh [options]
  --catalog-ssh HOST   Run collector commands over SSH (default: local)
  --harvester PATH     stac-harvester path on the collector host
  --ca-bundle PATH     Combined trusted CA bundle on the collector host
  --reuse-stack        Reuse running Hillview; still prepare the collector
  --heavy              Add the production-shaped corpus and churn checks
  --keep-load          Retain the heavy corpus after testing
  --no-seed            Reuse a retained heavy corpus manifest; upload fixtures stay isolated
  --cleanup-load       Withdraw and remove the retained heavy corpus
  --keep-up            Keep a local collector started by this script running
  --down               Stop the selected collector stack
Environment: META_CATALOG, WORK_DIR, CATALOG_DB, INSTANCE_NAME, PANORAMAX_URL,
             LOAD_PHOTOS=50000 LOAD_USERS=40 LOAD_YEARS=3 LOAD_SEED=1
All test assertions are shared between local and SSH collectors.
HELP
            exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

# Quote argv once for the remote user's login shell (which may be fish).
collector_exec() {
    if [ -n "$CATALOG_SSH" ]; then
        local remote_command
        remote_command=$(python3 -c 'import shlex,sys; print(shlex.join(sys.argv[1:]))' "$@")
        ssh -o BatchMode=yes "$CATALOG_SSH" "$remote_command"
    else
        "$@"
    fi
}

if [ "$DOWN" = 1 ]; then
    collector_exec docker compose -f "$META_CATALOG/docker-compose.yml" down
    exit 0
fi

cd "$REPO_ROOT"
set -a
source .env
source .env.dev
set +a
PANORAMAX_URL="${PANORAMAX_URL:-${PANORAMAX_BASE_URL:-http://localhost:8058}}"
CATALOG_HARVESTER="${CATALOG_HARVESTER:-$WORK_DIR/venv/bin/stac-harvester}"

if [ "$REUSE_STACK" = 0 ]; then
    ./compose.sh --profile panoramax up --build -d postgres api worker panoramax
fi
./backend/scripts/provision_panoramax_role.sh
for attempt in {1..60}; do
    if curl -sf "$PANORAMAX_URL/api/health" >/dev/null; then break; fi
    if [ "$attempt" = 60 ]; then echo 'Panoramax database health check timed out' >&2; exit 1; fi
    sleep 2
done

# Preserve a collector which was already running. Remote collectors stay up.
STOP_LOCAL=0
if [ -z "$CATALOG_SSH" ] && [ "$KEEP_UP" = 0 ] && \
   [ -z "$(docker compose -f "$META_CATALOG/docker-compose.yml" ps --status running -q database)" ]; then
    STOP_LOCAL=1
fi
cleanup() {
    if [ "$STOP_LOCAL" = 1 ]; then
        docker compose -f "$META_CATALOG/docker-compose.yml" down
    fi
}
trap cleanup EXIT

collector_exec bash -s -- "$META_CATALOG" "$CATALOG_HARVESTER" <<'BOOTSTRAP'
set -euo pipefail
meta=$1
harvester=$2
docker compose -f "$meta/docker-compose.yml" up -d database migrations </dev/null
for attempt in {1..60}; do
    if docker compose -f "$meta/docker-compose.yml" exec -T database psql -U username -d panoramax -tA -c "SELECT to_regclass('public.instances') IS NOT NULL" </dev/null 2>/dev/null | tr -d '\r' | grep -qx t; then break; fi
    if [ "$attempt" = 60 ]; then echo 'Collector migration readiness timed out' >&2; exit 1; fi
    sleep 2
done
if [ ! -x "$harvester" ]; then
    venv=$(dirname "$(dirname "$harvester")")
    uv venv "$venv" --quiet </dev/null
    uv pip install --python "$venv/bin/python" --quiet -e "$meta/harvester" 'pystac[validation]' </dev/null
fi
BOOTSTRAP

if [ -z "$CATALOG_SSH" ] && [ -z "$CATALOG_CA_BUNDLE" ] && \
   docker exec caddy-caddy-1 cat /data/caddy/pki/authorities/local/root.crt > /tmp/hillview-e2e-public-root.crt 2>/dev/null; then
    mkdir -p "$WORK_DIR"
    CATALOG_CA_BUNDLE="$WORK_DIR/ca-bundle.pem"
    "$(dirname "$CATALOG_HARVESTER")/python" - "$CATALOG_CA_BUNDLE" <<'CA'
from pathlib import Path
import certifi,sys
Path(sys.argv[1]).write_bytes(Path(certifi.where()).read_bytes()+b'\n'+Path('/tmp/hillview-e2e-public-root.crt').read_bytes())
CA
fi

RUN_ARGS+=(--harvester "$CATALOG_HARVESTER" --catalog-db "$CATALOG_DB"
    --instance-name "$INSTANCE_NAME" --panoramax-url "$PANORAMAX_URL" --work-dir "$WORK_DIR")
if [ -n "$CATALOG_SSH" ]; then RUN_ARGS+=(--catalog-ssh "$CATALOG_SSH"); fi
if [ -n "$CATALOG_CA_BUNDLE" ]; then RUN_ARGS+=(--ca-bundle "$CATALOG_CA_BUNDLE"); fi
export HILLVIEW_INSECURE_TLS="${HILLVIEW_INSECURE_TLS:-1}"
cd backend
uv run --quiet --frozen --package hillview-tests python panoramax/scripts/e2e_federation.py "${RUN_ARGS[@]}"
