#!/bin/bash
# Debug wrapper script for using test utilities
set -e

# Resolve the backend directory without changing CWD
BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"

# Set up environment
export PYTHONPATH="$BACKEND_DIR:$BACKEND_DIR/tests:$PYTHONPATH"

# Find python executable - prefer venv if it exists
if [[ -f "$BACKEND_DIR/tests/venv/bin/python" ]]; then
    PYTHON="$BACKEND_DIR/tests/venv/bin/python"
elif [[ -f "$BACKEND_DIR/venv/bin/python" ]]; then
    PYTHON="$BACKEND_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

# Run the debug utility
exec $PYTHON -c "
import sys
sys.path.insert(0, '$BACKEND_DIR/tests')
from utils.debug_utils import main
main()
" "$@"
