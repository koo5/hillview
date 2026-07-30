import time

from fastapi import APIRouter

from .. import db, graph

router = APIRouter()


async def _check(name: str, coro) -> dict:
    t0 = time.monotonic()
    try:
        await coro
        return {"dep": name, "ok": True, "ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as e:
        return {"dep": name, "ok": False, "ms": round((time.monotonic() - t0) * 1000, 1),
                "error": f"{type(e).__name__}: {e}"}


@router.get("/health")
async def health():
    checks = [
        await _check("workbench-db", db.ping(db.wb_engine)),
        await _check("hillview-db", db.ping(db.hv_engine)),
        await _check("oxigraph", graph.store.ping()),
    ]
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
