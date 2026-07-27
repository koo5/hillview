"""Terrain bench API: enqueue depth-panorama renders for photo viewpoints
(or ad-hoc lat/lon), receive worker results, serve the artifacts the bench
viewer needs (raw uint16 depth buffer + preview JPEG + meta), and provide
OSM natural=peak candidates for the viewer's peak labels."""
import gzip
import json
import math
import os
import tempfile
import time
import uuid

import httpx

from fastapi import (APIRouter, File, Form, Header, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text

from .. import config
from ..db import wb_engine

router = APIRouter()

WORKER_TOKEN = os.getenv("ENRICH_WORKER_TOKEN", "dev-worker-token")

# render() kwargs a client may set; mirrored in worker.py (defense on both ends).
ALLOWED_PARAMS = {"observer_height_m", "observer_elevation_m",
                  "gps_altitude_m", "gps_datum",
                  "az_start", "az_end", "az_step_deg",
                  "elev_min_deg", "elev_max_deg", "elev_step_deg",
                  "min_distance_m", "max_distance_m", "rel_step", "refraction_k"}


class EnqueueRequest(BaseModel):
    photo_id: str | None = None      # viewpoint from photo_mirror…
    lat: float | None = None         # …or an ad-hoc point
    lon: float | None = None
    params: dict = {}


@router.post("/terrain/enqueue")
async def enqueue(req: EnqueueRequest):
    from .. import actors
    if not actors.init_broker():
        raise HTTPException(503, "no RABBITMQ_URL configured")
    params = {k: v for k, v in (req.params or {}).items() if k in ALLOWED_PARAMS}

    lat, lon = req.lat, req.lon
    if req.photo_id:
        async with wb_engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT ST_Y(geometry) AS lat, ST_X(geometry) AS lon, altitude "
                "FROM photo_mirror WHERE id = :id AND geometry IS NOT NULL"),
                {"id": req.photo_id})).first()
        if not row:
            raise HTTPException(404, "photo not found or has no position")
        lat, lon = row.lat, row.lon
        # GPS altitude is passed as a HINT, never as a trusted elevation: the
        # worker resolves its datum (orthometric vs ellipsoidal — EXIF doesn't
        # say, and the CZ geoid undulation is ~44.5 m, a rozhledna's worth)
        # against the bare-earth ground and clamps implausible fixes. See
        # renderer.resolve_eye_elevation; provenance lands in meta.eye_source.
        if row.altitude is not None and "gps_altitude_m" not in params:
            params["gps_altitude_m"] = row.altitude
    if lat is None or lon is None:
        raise HTTPException(422, "need photo_id or lat+lon")

    async with wb_engine.begin() as conn:
        rid = (await conn.execute(text(
            "INSERT INTO terrain_renders (photo_id, lat, lon, params) "
            "VALUES (:pid, :lat, :lon, CAST(:p AS jsonb)) RETURNING id"),
            {"pid": req.photo_id, "lat": lat, "lon": lon,
             "p": json.dumps(params)})).scalar_one()
    # No callback URL or token in the message: the worker takes both from ITS
    # environment (TERRAIN_CALLBACK_URL / ENRICH_WORKER_TOKEN), so a
    # compromised broker can't redirect artifacts or read the secret.
    actors.render_panorama.send({
        "result_id": str(rid), "lat": lat, "lon": lon, "params": params,
    })
    print(f"terrain: enqueued {rid} @ ({lat:.5f}, {lon:.5f})", flush=True)
    return {"queued": str(rid)}


@router.post("/terrain/result")
async def result(result_json: str = Form(...),
                 depth: UploadFile | None = File(None),
                 preview: UploadFile | None = File(None),
                 x_worker_token: str = Header(None)):
    if x_worker_token != WORKER_TOKEN:
        raise HTTPException(403, "bad worker token")
    d = json.loads(result_json)
    try:
        # canonical uuid BEFORE any filesystem use: result_id names artifact
        # files, and the CAST in the UPDATE below would reject a traversal
        # payload only after the bytes had already landed on disk
        rid = str(uuid.UUID(str(d["result_id"])))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "result_id must be a uuid")

    tdir = os.path.join(config.ARTIFACTS_DIR, "terrain")
    os.makedirs(tdir, exist_ok=True)
    depth_path = preview_path = None
    if depth is not None:
        depth_path = os.path.join("terrain", f"{rid}.depth.bin")
        _write_atomic(_artifact_abspath(depth_path),
                      await depth.read(), gzip_too=True)
    if preview is not None:
        preview_path = os.path.join("terrain", f"{rid}.preview.jpg")
        _write_atomic(_artifact_abspath(preview_path),
                      await preview.read())

    if d.get("status") == "rendering":
        # Progress ping OR a streamed partial panorama (v1.5): meta jsonb is
        # MERGED, so a %-only ping between milestones can't wipe the partial's
        # grid meta / artifact_version; artifact paths update only when files
        # actually arrived. The status guard keeps an out-of-order late ping
        # from regressing a finished/failed render.
        async with wb_engine.begin() as conn:
            await conn.execute(text(
                "UPDATE terrain_renders SET status = 'rendering', "
                "meta = COALESCE(meta, '{}'::jsonb) || CAST(:meta AS jsonb), "
                "depth_path = COALESCE(:dp, depth_path), "
                "preview_path = COALESCE(:pp, preview_path), worker = :w "
                "WHERE id = CAST(:id AS uuid) AND status NOT IN ('done', 'error')"),
                {"meta": json.dumps(d.get("meta") or {}), "dp": depth_path,
                 "pp": preview_path, "w": d.get("worker"), "id": rid})
        return {"ok": True}
    async with wb_engine.begin() as conn:
        await conn.execute(text(
            "UPDATE terrain_renders SET status = :st, error = :err, "
            "meta = CAST(:meta AS jsonb), depth_path = :dp, preview_path = :pp, "
            "worker = :w, finished_at = now() WHERE id = CAST(:id AS uuid)"),
            {"st": d.get("status", "done"), "err": d.get("error"),
             "meta": json.dumps(d.get("meta")) if d.get("meta") else None,
             "dp": depth_path, "pp": preview_path, "w": d.get("worker"), "id": rid})
    return {"ok": True}


# "Queued with zero consumers" is otherwise perfectly silent (the worker is a
# host process the stack can't see), so the renders poll carries the terrain
# queue's message/consumer counts and the client can say "no worker connected".
# Passive declare over a short-lived connection, TTL-cached so the 3 s poll
# doesn't churn broker connections.
QUEUE_STATE_TTL_S = 5.0
_queue_state_cache: tuple[float, dict | None] | None = None


def _queue_state_now() -> dict | None:
    url = os.getenv("RABBITMQ_URL")
    if not url:
        return None
    import amqpstorm
    try:
        with amqpstorm.UriConnection(f"amqp://{url}?timeout=3") as conn:
            with conn.channel() as ch:
                d = ch.queue.declare("terrain", passive=True)
                return {"messages": d["message_count"],
                        "consumers": d["consumer_count"]}
    except amqpstorm.AMQPError:
        return None  # unreachable broker / missing queue → "unknown", not an error


async def _queue_state() -> dict | None:
    global _queue_state_cache
    if (_queue_state_cache
            and time.monotonic() - _queue_state_cache[0] < QUEUE_STATE_TTL_S):
        return _queue_state_cache[1]
    from starlette.concurrency import run_in_threadpool
    state = await run_in_threadpool(_queue_state_now)
    _queue_state_cache = (time.monotonic(), state)
    return state


@router.get("/terrain/renders")
async def renders(photo_id: str | None = None, limit: int = 50):
    where = "WHERE photo_id = :pid" if photo_id else ""
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, photo_id, lat, lon, params, status, error, meta, "
            "depth_path IS NOT NULL AS has_depth, "
            "preview_path IS NOT NULL AS has_preview, worker, "
            "enqueued_at, finished_at FROM terrain_renders "
            f"{where} ORDER BY enqueued_at DESC LIMIT :lim"),
            {"pid": photo_id, "lim": limit})).mappings().all()
    return {"renders": [dict(r) | {"id": str(r["id"])} for r in rows],
            "queue": await _queue_state()}


def _artifact_abspath(rel: str) -> str:
    """Resolve an artifact-relative path under ARTIFACTS_DIR, refusing any
    result that escapes it (symlinks included). Both the write side (worker
    results) and the serve side (paths read back from the DB) go through
    here, so no stored or supplied path can reach the wider filesystem."""
    root = os.path.realpath(config.ARTIFACTS_DIR)
    full = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([root, full]) != root:
        raise HTTPException(400, "artifact path escapes the artifacts dir")
    return full


def _write_atomic(path: str, data: bytes, gzip_too: bool = False) -> None:
    """Partials overwrite the same artifact paths while clients may be mid-
    download; temp + os.replace keeps every served byte-range self-consistent.
    gzip_too maintains a .gz sibling (refinement 4: raw uint16 depth shrinks
    well) served via Content-Encoding when the client accepts it."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    if gzip_too:
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "wb") as f:
            f.write(gzip.compress(data, compresslevel=6))
        os.replace(tmp, path + ".gz")


async def _artifact(render_id: str, col: str) -> str:
    async with wb_engine.connect() as conn:
        path = (await conn.execute(text(
            f"SELECT {col} FROM terrain_renders WHERE id = CAST(:id AS uuid)"),
            {"id": render_id})).scalar()
    if not path:
        raise HTTPException(404, "artifact not available")
    return _artifact_abspath(path)


@router.get("/terrain/renders/{render_id}/depth")
async def depth_artifact(render_id: str, request: Request):
    path = await _artifact(render_id, "depth_path")
    gz = path + ".gz"
    if "gzip" in request.headers.get("accept-encoding", "") and os.path.exists(gz):
        return FileResponse(gz, media_type="application/octet-stream",
                            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return FileResponse(path, media_type="application/octet-stream")


@router.get("/terrain/renders/{render_id}/preview")
async def preview_artifact(render_id: str):
    return FileResponse(await _artifact(render_id, "preview_path"),
                        media_type="image/jpeg")


# ---------------------------------------------------------------------------
# peak candidates (terrain-mode v2: OSM natural=peak labels)
# ---------------------------------------------------------------------------
# The client draws labels for peaks the RENDER can see — visibility is
# decided client-side against the depth buffer, so this endpoint only has to
# answer "which named peaks are in range". Overpass results are cached long
# (peaks don't move) keyed on a coarse grid, so nearby viewpoints share an
# entry and Overpass sees us rarely.

OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
# overpass-api.de 406es default library User-Agents (usage policy wants an
# identifying one) — send who we are, overridable for other instances
OVERPASS_UA = os.getenv("OVERPASS_USER_AGENT",
                        "hillview-enrich-terrain/1.0 (+https://github.com/koo5/hillview)")
PEAKS_TTL_S = 7 * 24 * 3600
PEAKS_MAX = 400
_peaks_cache: dict[tuple, tuple[float, list[dict]]] = {}


def parse_ele(v) -> float | None:
    """OSM ele values arrive as '1602', '1602.4', '1602 m', '1,602'…"""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None


def peaks_from_overpass(data: dict, limit: int = PEAKS_MAX) -> list[dict]:
    """Overpass JSON → [{name, lat, lon, ele}], highest first (when several
    hundred candidates exist, the tall ones are the ones worth labeling)."""
    out = []
    for el in data.get("elements", []):
        name = (el.get("tags") or {}).get("name")
        lat, lon = el.get("lat"), el.get("lon")
        if not name or lat is None or lon is None:
            continue
        out.append({"name": name, "lat": lat, "lon": lon,
                    "ele": parse_ele((el.get("tags") or {}).get("ele"))})
    out.sort(key=lambda p: p["ele"] if p["ele"] is not None else -math.inf,
             reverse=True)
    return out[:limit]


@router.get("/terrain/peaks")
async def peaks(lat: float, lon: float, radius_m: float = 100_000.0):
    radius_m = max(1_000.0, min(radius_m, 200_000.0))
    key = (round(lat, 2), round(lon, 2), round(radius_m, -3))  # ~1 km grid
    hit = _peaks_cache.get(key)
    if hit and time.monotonic() - hit[0] < PEAKS_TTL_S:
        return {"peaks": hit[1], "cached": True}
    query = (f"[out:json][timeout:25];"
             f'node["natural"="peak"]["name"](around:{radius_m:.0f},{lat},{lon});'
             f"out body;")
    try:
        async with httpx.AsyncClient(timeout=30,
                                     headers={"User-Agent": OVERPASS_UA}) as client:
            r = await client.post(OVERPASS_URL, data={"data": query})
            r.raise_for_status()
            result = peaks_from_overpass(r.json())
    except httpx.HTTPError as e:
        # a stale cache entry beats an error for a label overlay
        if hit:
            return {"peaks": hit[1], "cached": True, "stale": True}
        raise HTTPException(502, f"overpass: {e}")
    _peaks_cache[key] = (time.monotonic(), result)
    return {"peaks": result}
