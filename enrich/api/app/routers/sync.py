import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import sync as sync_mod
from ..db import wb_engine

router = APIRouter()


class SyncRequest(BaseModel):
    mode: str = "append"   # append | reconcile


@router.post("/sync/run")
async def sync_run(req: SyncRequest):
    if req.mode not in ("append", "reconcile"):
        raise HTTPException(422, "mode must be append or reconcile")
    if sync_mod.sync_lock.locked():
        raise HTTPException(409, "a sync is already running")

    async def _job():
        async with sync_mod.sync_lock:
            try:
                await sync_mod.run_sync(req.mode)
            except Exception as e:
                print(f"sync {req.mode} failed: {e}", flush=True)

    asyncio.create_task(_job())
    return {"started": req.mode}


@router.get("/sync/status")
async def sync_status():
    async with wb_engine.connect() as conn:
        state = [dict(r._mapping) for r in (await conn.execute(text(
            "SELECT * FROM sync_state ORDER BY table_name"))).all()]
        counts = {}
        for t in ("photo_mirror", "annotation_mirror"):
            counts[t] = dict((await conn.execute(text(
                f"SELECT count(*) AS total, "
                f"count(*) FILTER (WHERE missing_since IS NOT NULL) AS missing "
                f"FROM {t}"))).first()._mapping)
        last = [dict(r._mapping) for r in (await conn.execute(text(
            "SELECT id, kind, status, started_at, finished_at, stats, error "
            "FROM runs WHERE kind LIKE 'sync_%' "
            "ORDER BY started_at DESC LIMIT 5"))).all()]
    return {"running": sync_mod.sync_lock.locked(), "state": state,
            "counts": counts, "last_runs": last}
