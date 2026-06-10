#!/usr/bin/env bash
# Canonical `docker compose` wrapper for the hillview dev stack.
#
# Pins the two things that are easy to get wrong by hand:
#   - env-file order: .env (base) first, .env.dev (dev overrides) last → dev wins
#   - both compose files: docker-compose.yml + docker-compose.dev.yml
#
# Everything after is passed straight through to `docker compose`, so use it
# for any subcommand:
#   ./compose.sh up --build -d        # bring the stack up
#   ./compose.sh up --build -d api    # just the api
#   ./compose.sh logs -f api
#   ./compose.sh ps
#   ./compose.sh down
#
# Note: the dev stack uses host networking, so the api binds the host's socket
# directly. It listens on `::` (IPv6 wildcard, dual-stack) so it answers on both
# IPv4 (localhost) and IPv6 (e.g. a Yggdrasil .internal address).
set -euo pipefail

cd "$(dirname "$(readlink -f -- "$0")")"

exec docker compose \
    --env-file .env \
    --env-file .env.dev \
    -f docker-compose.yml \
    -f docker-compose.dev.yml \
    "$@"
