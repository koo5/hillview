#!/bin/bash
# Debug wrapper script for using test utilities
set -e

# Change to the correct directory
cd "$(dirname "$0")"

# Check if we're in tests directory, if so go up one level
if [[ $(basename "$PWD") == "tests" ]]; then
    cd ..
fi

# Set up environment
export PYTHONPATH=".:tests:$PYTHONPATH"

# Find python executable - prefer venv if it exists
if [[ -f "tests/venv/bin/python" ]]; then
    PYTHON="tests/venv/bin/python"
elif [[ -f "venv/bin/python" ]]; then
    PYTHON="venv/bin/python"
else
    PYTHON="python3"
fi

# Run the debug utility
exec $PYTHON -c "
import sys
sys.path.insert(0, 'tests')
from utils.debug_utils import main
main()
" "$@"