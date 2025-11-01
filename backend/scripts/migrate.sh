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
API_APP_DIR="$BACKEND_DIR/api/app"

# Change to the backend directory to ensure .env is loaded correctly
cd "$BACKEND_DIR"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: No .env file found in $BACKEND_DIR"
    echo "Using default database connection settings"
fi

echo "Running alembic migration: $*"
echo "Backend directory: $BACKEND_DIR"
echo "Working directory: api/app"

# Run alembic with current .env file loaded
docker run --rm --network hillview_network \
    -v "$BACKEND_DIR:/app" \
    -w "/app/api/app" \
    --env-file .env \
    -e ALEMBIC_SYNC_MODE=1 \
    hillview-api:latest alembic "$@"
