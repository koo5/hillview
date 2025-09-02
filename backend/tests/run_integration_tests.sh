#!/bin/bash

cd "$(dirname "$(readlink -f -- "$0")")"

# Create test virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating test virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install backend dev dependencies (includes app + test dependencies)
echo "Installing backend dev dependencies..."
pip install -q -r ../api/app/requirements-dev.txt

# Install additional integration test dependencies
echo "Installing integration test dependencies..."
pip install -q -r requirements.txt

# Run integration tests
if [ $# -eq 0 ]; then
    echo "Running all integration tests..."
    python -m pytest integration/ -v
    set_exit=$?
else
    echo "Running integration tests: $*"
    python -m pytest "$@"
    set_exit=$?
fi

# Deactivate virtual environment
deactivate

exit $set_exit
