#!/usr/bin/env bash
# Bring up the hillview stack. Waits for the api to respond before exiting.
# For the pics file server on :9999, also run: cd caddy && docker compose up -d
set -euo pipefail

cd "$(dirname "$(readlink -f -- "$0")")/../.."

# Delegate to the canonical wrapper so env-file order / compose files stay in
# one place (see compose.sh).
./compose.sh up --build --remove-orphans -d

for _ in $(seq 1 60); do
    if curl -fsS http://localhost:8055/api/debug >/dev/null 2>&1; then
        echo "api ready at http://localhost:8055"
        exit 0
    fi
    sleep 2
done

echo "api did not respond within 120s"
exit 1
