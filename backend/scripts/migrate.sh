#!/bin/bash
# Database migration script for Hillview backend
# Usage: ./scripts/migrate.sh [alembic command and args]
# Examples:
#   ./scripts/migrate.sh heads
#   ./scripts/migrate.sh upgrade head  
#   ./scripts/migrate.sh history
#   ./scripts/migrate.sh current

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