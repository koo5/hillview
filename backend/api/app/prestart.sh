#!/bin/bash

# Pre-start script to run database migrations
set -e

echo "========================================="
echo "HILLVIEW PRESTART SCRIPT v2 - $(date)"
echo "========================================="

# Only run migrations on the first worker (when GUNICORN_PROCESS_INDEX is not set or is 0)
if [ "${GUNICORN_PROCESS_INDEX:-0}" = "0" ]; then
    echo "Running database migrations (worker 0)..."
    cd /app/app
    alembic upgrade head
    echo "Migrations completed successfully!"
else
    echo "Skipping migrations (worker ${GUNICORN_PROCESS_INDEX})"
fi

echo "========================================="