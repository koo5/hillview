#!/bin/bash
# Provision the panoramax_ro role on an EXISTING deployment (initdb.d only runs
# on fresh clusters). Idempotent: safe to re-run; re-applies grants.
#
# Usage (from repo root, with .env loaded or POSTGRES_* + PANORAMAX_DB_PASSWORD
# exported):
#     ./backend/scripts/provision_panoramax_role.sh
#
# Must run AFTER migration 030_add_panoramax_schema (the grants reference the
# panoramax schema). Migration 030 also applies these grants itself when the
# role already exists, so on fresh clusters this script is unnecessary.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${PANORAMAX_DB_PASSWORD:?PANORAMAX_DB_PASSWORD is required}"

CONTAINER="${POSTGRES_CONTAINER:-hillview_postgres}"

# '' -escape any single quotes so the password can't break the SQL literal
ESCAPED_PW="${PANORAMAX_DB_PASSWORD//\'/\'\'}"

docker exec -i "$CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<EOSQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panoramax_ro') THEN
        CREATE ROLE panoramax_ro LOGIN;
    END IF;
END \$\$;
ALTER ROLE panoramax_ro PASSWORD '$ESCAPED_PW';
GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO panoramax_ro;
GRANT USAGE ON SCHEMA public TO panoramax_ro;
GRANT SELECT ON photos, users, photo_ratings, flagged_photos TO panoramax_ro;
GRANT USAGE ON SCHEMA panoramax TO panoramax_ro;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON panoramax.sequences, panoramax.sequence_photos TO panoramax_ro;
EOSQL

echo "panoramax_ro provisioned."
