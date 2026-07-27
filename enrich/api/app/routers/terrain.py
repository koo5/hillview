"""Terrain bench API: enqueue depth-panorama renders for photo viewpoints
(or ad-hoc lat/lon), receive worker results, serve the artifacts the bench
viewer needs (raw uint16 depth buffer + preview JPEG + meta), and provide
OSM label candidates (peaks, observation towers, masts) for the viewer."""
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

# render() kwargs a client may set; mirrored in worker.py (defense on both
# ends). dsm_stack is not a render() kwarg: the worker maps it to a named
# TERRAIN_DSM_PATH_<STACK> env stack (glo30 / cuzk).
ALLOWED_PARAMS = {"observer_height_m", "observer_elevation_m",
                  "gps_altitude_m", "gps_datum", "dsm_stack",
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
                "SELECT ST_Y(geometry) AS lat, ST_X(geometry) AS lon, altitude, "
                "compass_angle, width, height "
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
        # Photos with a known bearing render only their view wedge (pie:
        # calibrated FOV when available, compass ± assumed 90° otherwise)
        # + margin — no point marching 360° for a photograph, pano or not.
        # Explicit az params always win; wedges that would cover the whole
        # circle anyway fall back to the full sweep.
        if "az_start" not in params and "az_end" not in params:
            from .matching import _pano_pie
            pie = await _pano_pie(req.photo_id, row.compass_angle,
                                  slack=2.0, default_far=2000, assumed_fov=90)
            margin = 5.0
            if pie and 2 * (pie["half"] + margin) < 360:
                params["az_start"] = pie["bearing"] - pie["half"] - margin
                params["az_end"] = pie["bearing"] + pie["half"] + margin
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
    where = "WHERE tr.photo_id = :pid" if photo_id else ""
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT tr.id, tr.photo_id, pm.title AS photo_title, "
            "tr.lat, tr.lon, tr.params, tr.status, tr.error, tr.meta, "
            "tr.depth_path IS NOT NULL AS has_depth, "
            "tr.preview_path IS NOT NULL AS has_preview, tr.worker, "
            "tr.enqueued_at, tr.finished_at FROM terrain_renders tr "
            "LEFT JOIN photo_mirror pm ON pm.id = tr.photo_id "
            f"{where} ORDER BY tr.enqueued_at DESC LIMIT :lim"),
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
# label candidates (terrain-mode v2: OSM peaks + observation towers/masts)
# ---------------------------------------------------------------------------
# The client draws labels for features the RENDER can see — visibility is
# decided client-side against the depth buffer, so this endpoint only has to
# answer "which named features are in range". UNCAPPED on purpose: the old
# global top-400-by-ele cap measured at Prosek kept nothing nearer than
# 55 km and dropped Říp (oneoff probes 2026-07-27). Overpass results are
# cached long (peaks don't move) keyed on a coarse grid, so nearby
# viewpoints share an entry and Overpass sees us rarely.
#
# Overpass [timeout:N] is a KILL switch, not a best-effort budget: a query
# either completes fully or aborts, and an abort surfaces as a "remark" in
# the JSON — which we treat as failure and never cache.

OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
# overpass-api.de 406es default library User-Agents (usage policy wants an
# identifying one) — send who we are, overridable for other instances
OVERPASS_UA = os.getenv("OVERPASS_USER_AGENT",
                        "hillview-enrich-terrain/1.0 (+https://github.com/koo5/hillview)")
# DSM for filling missing OSM ele tags (half the named peaks in the Prosek
# pool lack one and would otherwise be unrankable). The api mounts the earth
# volume read-only; a SURFACE model also gives towers/masts their visible
# top height rather than the ground at their base.
PEAKS_DEM = os.getenv("PEAKS_DEM_PATH", "/dem/glo30.vrt")
PEAKS_TTL_S = 7 * 24 * 3600
_peaks_cache: dict[tuple, tuple[float, list[dict]]] = {}


def parse_ele(v) -> float | None:
    """OSM ele/prominence values arrive as '1602', '1602.4', '1602 m', '1,602'…"""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None


def features_from_overpass(data: dict) -> list[dict]:
    """Overpass JSON (peaks ∪ towers/masts union) → candidate dicts.
    kind: peak | tower (observation) | mast (communication). prominence rides
    along where OSM has it (~2% of peaks — but precisely the famous ones):
    the client uses it for label priority now that the pool is uncapped."""
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name, lat, lon = tags.get("name"), el.get("lat"), el.get("lon")
        if not name or lat is None or lon is None:
            continue
        if tags.get("natural") == "peak":
            kind = "peak"
        elif tags.get("tower:type") == "observation":
            kind = "tower"
        else:
            kind = "mast"
        f = {"name": name, "lat": lat, "lon": lon, "kind": kind,
             "ele": parse_ele(tags.get("ele"))}
        prom = parse_ele(tags.get("prominence"))
        if prom is not None:
            f["prominence"] = prom
        out.append(f)
    return out


def fill_missing_ele(feats: list[dict]) -> None:
    """Sample the DSM at features whose OSM ele tag is missing (sync — run
    via threadpool). Estimates are flagged; on any failure candidates simply
    keep ele None — labels still work, only ranking degrades."""
    missing = [f for f in feats if f["ele"] is None]
    if not missing or not os.path.exists(PEAKS_DEM):
        return
    try:
        import rasterio
        with rasterio.open(PEAKS_DEM) as src:
            samples = src.sample([(f["lon"], f["lat"]) for f in missing])
            for f, v in zip(missing, samples):
                val = float(v[0])
                if math.isfinite(val) and val > -1000:
                    f["ele"] = round(val, 1)
                    f["ele_estimated"] = True
    except Exception as e:  # noqa: BLE001
        print(f"terrain: DEM ele fill failed: {e}", flush=True)


@router.get("/terrain/peaks")
async def peaks(lat: float, lon: float, radius_m: float = 100_000.0):
    radius_m = max(1_000.0, min(radius_m, 200_000.0))
    key = (round(lat, 2), round(lon, 2), round(radius_m, -3))  # ~1 km grid
    hit = _peaks_cache.get(key)
    if hit and time.monotonic() - hit[0] < PEAKS_TTL_S:
        return {"peaks": hit[1], "cached": True}
    around = f"around:{radius_m:.0f},{lat},{lon}"
    query = (
        f"[out:json][timeout:60];("
        f'node["natural"="peak"]["name"]({around});'
        f'node["man_made"~"^(tower|mast)$"]'
        f'["tower:type"~"^(observation|communication)$"]["name"]({around});'
        f");out body;")
    try:
        async with httpx.AsyncClient(timeout=90,
                                     headers={"User-Agent": OVERPASS_UA}) as client:
            r = await client.post(OVERPASS_URL, data={"data": query})
            r.raise_for_status()
            data = r.json()
            if data.get("remark"):
                raise HTTPException(502, f"overpass aborted: {data['remark']}")
            result = features_from_overpass(data)
    except (httpx.HTTPError, ValueError) as e:
        # a stale cache entry beats an error for a label overlay
        if hit:
            return {"peaks": hit[1], "cached": True, "stale": True}
        raise HTTPException(502, f"overpass: {e}")
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(fill_missing_ele, result)
    result.sort(key=lambda p: p["ele"] if p["ele"] is not None else -math.inf,
                reverse=True)
    _peaks_cache[key] = (time.monotonic(), result)
    return {"peaks": result}
