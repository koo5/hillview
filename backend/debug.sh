#!/bin/bash
# Debug wrapper script for using test utilities
set -e

# Resolve the backend directory without changing CWD
BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"

# Set up environment
export PYTHONPATH="$BACKEND_DIR:$BACKEND_DIR/tests:$PYTHONPATH"

# The uv-managed workspace env, and ONLY that. No interpreter-guessing ladder
# and no auto-sync here: this is a leaf CLI that callers (the pics pipeline's
# upload loop) invoke many times in parallel, so it must neither mutate the
# shared .venv mid-flight nor silently fall back to a stale/hand-made env —
# the old tests/venv fallback ran a Sep-2025 snapshot without PyJWT and broke
# every upload (2026-08-31). Env maintenance belongs to the session entry
# points (tests/run_integration_tests.sh syncs it; scripts/deps.py upgrades).
PYTHON="$BACKEND_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "debug.sh: no $PYTHON — materialize the locked env once:" >&2
    echo "  (cd $BACKEND_DIR && uv sync --frozen --package hillview-tests)" >&2
    exit 2
fi

# Run the debug utility
exec $PYTHON -c "
import sys
sys.path.insert(0, '$BACKEND_DIR/tests')
from utils.debug_utils import main
main()
" "$@"
