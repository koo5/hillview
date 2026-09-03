import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import sync as sync_mod
from ..db import wb_engine

router = APIRouter()


class SyncRequest(BaseModel):
    # one pass now; 'reconcile' still accepted as its historical name
    mode: str = "sync"


@router.post("/sync/run")
async def sync_run(req: SyncRequest = SyncRequest()):
    if req.mode == "append":
        raise HTTPException(422, sync_mod.APPEND_GONE)
    if req.mode not in ("sync", "reconcile"):
        raise HTTPException(422, "mode must be sync")
    if sync_mod.sync_lock.locked():
        raise HTTPException(409, "a sync is already running")

    async def _job():
        # sync_and_derive takes the sync lock itself (sync + parse), then chains
        # the scoped geocode run outside it
        try:
            await sync_mod.sync_and_derive(req.mode)
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
