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
# after a sync, derive facts for the rows it changed: parse their bodies (local,
# idempotent) and geocode them (external, paced, cached) — see sync.sync_and_derive
DERIVE_ON_SYNC = os.getenv("ENRICH_DERIVE_ON_SYNC", "1") in ("1", "true", "yes")
# schema file(s) applied idempotently at startup (see db.init_schema)
SCHEMA_DIR = os.getenv("SCHEMA_DIR", str(Path(__file__).parents[2] / "db" / "init"))
# Workbench web UI, plus the main hillview frontend's origins — its terrain
# mode (VITE_TERRAIN_API) calls this API cross-origin from the vite dev server
# (:8212), the built frontend container (:3000) or the Caddy h2 origin.
# Deliberately NOT "*": the API is unauthed, an allowlist keeps arbitrary
# websites from reading it via the user's browser.
# `or` (not a getenv default) so an empty compose passthrough falls back too.
CORS_ORIGINS = (
    os.getenv("ENRICH_CORS_ORIGINS")
    or "http://localhost:8071,http://127.0.0.1:8071,"
    "http://localhost:8212,http://127.0.0.1:8212,"
    "http://localhost:3000,http://127.0.0.1:3000,"
    "https://hillview.dev4.local"
).split(",")
