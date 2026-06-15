# Use NullPool for the DB engine in unit tests. The async engine is built at
# import time in common.database, so this must be set before the test modules
# (which `import api` -> common.database) are imported. pytest imports conftest.py
# before the test modules in its directory, so the var is set in time.
#
# Why: pooled asyncpg connections outlive the sync TestClient's event loop and,
# when GC'd at teardown, emit "coroutine 'Connection._cancel' was never awaited".
# NullPool closes (and awaits) each connection when its session closes.
import os

os.environ.setdefault("DB_NULLPOOL", "1")
