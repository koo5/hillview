#!/bin/bash

cd "$(dirname "$(readlink -f -- "$0")")"

# Create test virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating test virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install backend dependencies first (for FastAPI app imports)
echo "Installing backend dependencies..."
pip install -q -r ../api/app/requirements.txt

# Install test dependencies
echo "Installing test dependencies..."
pip install -q -r requirements.txt

# Run the tests
if [ $# -eq 0 ]; then
    echo "Running all tests..."
    python -m pytest integration/ unit/ -v
else
    echo "Running tests: $*"
    python -m pytest "$@"
fi

# Deactivate virtual environment
deactivate