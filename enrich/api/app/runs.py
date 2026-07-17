"""Runs-table helpers: every batch operation is a run row."""
import uuid
from typing import Any

import sqlalchemy as sa

from .db import wb_engine
from .tables import runs


async def create_run(kind: str, params: dict | None = None, note: str | None = None,
                     graph_iri: str | None = None) -> uuid.UUID:
    async with wb_engine.begin() as conn:
        row = (await conn.execute(
            runs.insert()
            .values(kind=kind, params=params or {}, note=note, graph_iri=graph_iri)
            .returning(runs.c.id)
        )).one()
    return row.id


async def finish_run(run_id: uuid.UUID, stats: dict | None = None,
                     graph_iri: str | None = None) -> None:
    values: dict[str, Any] = {"status": "succeeded", "finished_at": sa.func.now()}
    if stats is not None:
        values["stats"] = stats
    if graph_iri is not None:
        values["graph_iri"] = graph_iri
    async with wb_engine.begin() as conn:
        await conn.execute(runs.update().where(runs.c.id == run_id).values(**values))


async def fail_run(run_id: uuid.UUID, error: str) -> None:
    async with wb_engine.begin() as conn:
        await conn.execute(
            runs.update().where(runs.c.id == run_id)
            .values(status="failed", finished_at=sa.func.now(), error=error[:8000])
        )
