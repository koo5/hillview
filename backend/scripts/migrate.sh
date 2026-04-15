#!/bin/bash
# Database migration script for Hillview backend
# Usage: ./scripts/migrate.sh [alembic command and args]
# Examples:
#   ./scripts/migrate.sh heads
#   ./scripts/migrate.sh upgrade head
#   ./scripts/migrate.sh history
#   ./scripts/migrate.sh current

# best practices for managing Alembic migrations:
#  1. Use Sequential Numbering for Migration Names
#
#  Instead of letting Alembic generate random revision IDs, use a consistent numbering scheme:
#
#  # Good: Sequential numbering
#  001_initial_schema.py
#  002_add_user_profiles.py
#  003_add_photo_metadata.py
#  004_add_push_notifications.py
#
#  # Bad: Random revision IDs
#  4becdf297d3c_add_index.py
#  875cccae8edb_add_view.py
#
#  2. Always Check Migration Order Before Creating
#
#  # Before creating a new migration, check the current head
#  ./scripts/migrate.sh current
#
#  # Then create with proper dependencies
#  ./scripts/migrate.sh revision --autogenerate -m "010_your_feature_name"
#
#  3. Use Branch-Specific Naming When Working in Parallel
#
#  # When working on feature branches
#  010a_feature_auth_improvements.py  # auth branch
#  010b_feature_photo_processing.py   # photo branch
#  011_merge_auth_and_photo.py        # merge migration
#
#  4. Create Merge Migrations Immediately
#
#  When you have parallel development, create the merge migration right after merging branches:
#
#  # After merging branches with migrations
#  ./scripts/migrate.sh merge heads -m "merge_feature_branches"
#


set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$BACKEND_DIR")"
API_APP_DIR="$BACKEND_DIR/api/app"

# Change to the backend directory
cd "$BACKEND_DIR"

# .env file is always in repo root now
ENV_FILE="$REPO_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Warning: No .env file found in $REPO_ROOT"
    echo "Using default database connection settings"
    ENV_FILE=""
fi

echo "Running alembic migration: $*"
echo "Backend directory: $BACKEND_DIR"
echo "Working directory: api/app"

# Source env vars to construct DATABASE_URL
if [ -n "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Construct DATABASE_URL using localhost (for host network mode)
DB_USER="${POSTGRES_USER:-hillview}"
DB_PASS="${POSTGRES_PASSWORD:-hillview}"
DB_NAME="${POSTGRES_DB:-hillview}"
DB_PORT="${POSTGRES_HOST_PORT:-5432}"
DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}"

# Run alembic with host network
docker run --rm --network host \
    -v "$BACKEND_DIR:/app" \
    -w "/app/api/app" \
    -e ALEMBIC_SYNC_MODE=1 \
    -e DATABASE_URL="$DATABASE_URL" \
    hillview-api:latest alembic "$@"
