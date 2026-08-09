from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..db import wb_engine

router = APIRouter()


@router.get("/runs")
async def list_runs(kind: str | None = None, limit: int = 50, offset: int = 0):
    where = "WHERE kind = :kind" if kind else ""
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT id, kind, status, started_at, finished_at, graph_iri, stats, "
            f"error, note FROM runs {where} "
            f"ORDER BY started_at DESC LIMIT :limit OFFSET :offset"),
            {"kind": kind, "limit": min(limit, 500), "offset": offset})).all()
    return [dict(r._mapping) for r in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT * FROM runs WHERE id = CAST(:id AS uuid)"), {"id": run_id})).first()
    if not row:
        raise HTTPException(404, "run not found")
    return dict(row._mapping)
