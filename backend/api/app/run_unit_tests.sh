#!/bin/bash

cd "$(dirname "$(readlink -f -- "$0")")"

# Use the existing virtual environment from tests/venv
TEST_VENV="../../tests/venv"

# Create test virtual environment if it doesn't exist
if [ ! -d "$TEST_VENV" ]; then
    echo "Creating test virtual environment..."
    python3 -m venv "$TEST_VENV"
fi

# Activate virtual environment
source "$TEST_VENV/bin/activate"

# Install dev dependencies
echo "Installing API app dev dependencies..."
pip install -q -r requirements-dev.txt

# Add both current directory (api/app) and backend directory to Python path
# Current directory first so API app modules take precedence over common ones
export PYTHONPATH=".:../../../common:../..:$PYTHONPATH"

# Run unit tests
if [ $# -eq 0 ]; then
    echo "Running all unit tests..."
    python -m pytest tests/unit/ -v
    set_exit=$?
else
    echo "Running unit tests: $*"
    python -m pytest "$@"
    set_exit=$?
fi

# Deactivate virtual environment
deactivate

exit $set_exit
