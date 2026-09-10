import os
import shutil
import time

from fastapi import APIRouter

from .. import config, db, graph

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


# ----------------------------------------------------------------- machine health
# The day the root filesystem filled up, the bench answered every request with a 500
# and the only symptom on screen was "queue unknown". These are the numbers that would
# have said why, with thresholds that turn into warnings the dashboard can show in
# colour. The API runs in a container, but it shares the host kernel (so /proc/meminfo
# and /proc/loadavg are the host's) and the artifacts directory is a bind mount of the
# host filesystem the solves and the docker images live on.

DISK_WARN_GB = float(os.getenv("HEALTH_DISK_WARN_GB", "20"))
DISK_WARN_PCT = float(os.getenv("HEALTH_DISK_WARN_PCT", "90"))
RAM_WARN_GB = float(os.getenv("HEALTH_RAM_WARN_GB", "4"))


def _meminfo() -> dict:
    out = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                out[k] = int(v.strip().split()[0]) * 1024
    except OSError:
        pass
    return out


def _disk(path: str) -> dict | None:
    try:
        u = shutil.disk_usage(path)
    except OSError:
        return None
    return {"path": path, "total_gb": round(u.total / 2**30, 1),
            "free_gb": round(u.free / 2**30, 1),
            "used_pct": round(100 * (u.total - u.free) / max(u.total, 1), 1)}


@router.get("/health/machine")
async def machine():
    warnings = []
    disks = []
    for path in (config.ARTIFACTS_DIR, "/"):
        d = _disk(path)
        if d:
            disks.append(d)
            if d["free_gb"] < DISK_WARN_GB or d["used_pct"] > DISK_WARN_PCT:
                warnings.append(f"disk {path}: {d['free_gb']} GB free ({d['used_pct']}% used)")
    m = _meminfo()
    mem = None
    if m:
        avail = m.get("MemAvailable", 0)
        mem = {"total_gb": round(m.get("MemTotal", 0) / 2**30, 1),
               "available_gb": round(avail / 2**30, 1)}
        if avail / 2**30 < RAM_WARN_GB:
            warnings.append(f"memory: {mem['available_gb']} GB available")
    load = None
    try:
        with open("/proc/loadavg") as f:
            l1, l5, l15 = (float(x) for x in f.read().split()[:3])
        cores = os.cpu_count() or 1
        load = {"1m": l1, "5m": l5, "15m": l15, "cores": cores}
        if l5 > cores * 1.5:
            warnings.append(f"load {l5:.1f} on {cores} cores")
    except (OSError, ValueError):
        pass
    queue = None
    try:
        from .recon import _queue_state
        queue = await _queue_state()
        if queue and queue.get("messages") and not queue.get("consumers"):
            warnings.append(f"recon queue: {queue['messages']} message(s) and no worker")
    except Exception as e:
        queue = {"error": f"{type(e).__name__}: {e}"}
    return {"ok": not warnings, "warnings": warnings, "disks": disks, "memory": mem,
            "load": load, "recon_queue": queue, "at": time.time()}
