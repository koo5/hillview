"""Environment-driven configuration for the workbench API."""
import os
from pathlib import Path

WB_DB_URL = os.getenv(
    "WB_DB_URL",
    "postgresql+asyncpg://enrich:enrich@127.0.0.1:15432/enrich",
)
# Source-of-truth Hillview DB: READ ONLY (enforced per-connection in db.py).
# In-compose default resolves `postgres` over hillview_network; the host-run
# fallback targets the loopback publish of the dev stack.
HILLVIEW_DB_URL = os.getenv(
    "HILLVIEW_DB_URL",
    "postgresql+asyncpg://hillview:hillview@127.0.0.1:5432/hillview",
)
OXIGRAPH_URL = os.getenv("OXIGRAPH_URL", "http://127.0.0.1:7878")
ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", str(Path(__file__).parents[1] / "artifacts"))
ALLOW_RAW_UPDATE = os.getenv("ENRICH_ALLOW_RAW_UPDATE", "0") in ("1", "true", "yes")
# schema file(s) applied idempotently at startup (see db.init_schema)
SCHEMA_DIR = os.getenv("SCHEMA_DIR", str(Path(__file__).parents[2] / "db" / "init"))
CORS_ORIGINS = os.getenv(
    "ENRICH_CORS_ORIGINS",
    "http://localhost:8071,http://127.0.0.1:8071",
).split(",")
