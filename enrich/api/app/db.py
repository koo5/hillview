"""Two async engines: the workbench DB (rw) and the hillview source DB (read-only).

The hillview engine sets default_transaction_read_only=on per connection, so a
bug in sync code physically cannot write to the source. A real read-only role is
the prod step (design doc M5)."""
import glob
import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy import text

from . import config

wb_engine: AsyncEngine = create_async_engine(config.WB_DB_URL, pool_pre_ping=True)
hv_engine: AsyncEngine = create_async_engine(
    config.HILLVIEW_DB_URL,
    pool_pre_ping=True,
    connect_args={"server_settings": {"default_transaction_read_only": "on"}},
)


async def init_schema() -> list[str]:
    """Apply the idempotent schema files (the M0–M2 migration story).

    Executed through the raw asyncpg connection: multi-statement SQL needs the
    simple query protocol (prepared statements reject multiple commands)."""
    applied = []
    for path in sorted(glob.glob(os.path.join(config.SCHEMA_DIR, "*.sql"))):
        with open(path) as f:
            sql = f.read()
        async with wb_engine.connect() as conn:
            raw = await conn.get_raw_connection()
            await raw.driver_connection.execute(sql)
            await conn.commit()
        applied.append(os.path.basename(path))
    return applied


async def ping(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
