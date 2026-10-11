"""Make the analyzer modules importable and keep common.database from building an engine."""
import os
import sys
from pathlib import Path

# analyzer.py imports common.database, which only skips engine creation in alembic's sync mode.
# These tests exercise pure functions; no database is involved.
os.environ.setdefault("ALEMBIC_SYNC_MODE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
