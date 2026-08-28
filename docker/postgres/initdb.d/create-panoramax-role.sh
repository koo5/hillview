#!/bin/bash
set -e

# Create the dedicated role for the panoramax federation container (fresh
# clusters only — initdb.d never re-runs on an existing data volume; for those,
# run backend/scripts/provision_panoramax_role.sh instead).
#
# Only the role is created here: the panoramax schema and the photos/users
# tables don't exist yet at cluster-init time. The actual grants live in
# alembic migration 030_add_panoramax_schema, which applies them iff this role
# exists — and it will, because the api container runs migrations after
# postgres is up.
#
# Password comes from PANORAMAX_DB_PASSWORD on the postgres service. If unset,
# the role is skipped (the deployment just isn't running the panoramax
# container yet); provision later with the script above.

if [ -z "${PANORAMAX_DB_PASSWORD:-}" ]; then
    echo "PANORAMAX_DB_PASSWORD not set — skipping panoramax_ro role creation"
    exit 0
fi

# '' -escape any single quotes so the password can't break the SQL literal
ESCAPED_PW="${PANORAMAX_DB_PASSWORD//\'/\'\'}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE panoramax_ro LOGIN PASSWORD '${ESCAPED_PW}';
    GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO panoramax_ro;
EOSQL
