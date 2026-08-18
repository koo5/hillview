"""Terrain bench API: enqueue depth-panorama renders for photo viewpoints
(or ad-hoc lat/lon), receive worker results, serve the artifacts the bench
viewer needs (raw uint16 depth buffer + preview JPEG + meta), and provide
OSM label candidates (peaks, observation towers, masts, and settlement
place names) for the viewer."""
import asyncio
import gzip
import hashlib
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
# OSM peaks/places drift slowly — 60 d default, env-tunable. The DB layer
# below makes this TTL real: the in-process dict alone was wiped by every
# api reload (each deploy/edit), so first clients kept paying cold passes.
PEAKS_TTL_S = int(os.getenv("PEAKS_TTL_S", str(60 * 24 * 3600)))
# The candidate pool is fetched per FIXED GLOBAL TILE (0.5°×0.5°), not per
# request disc: one monolithic around:200km query (peaks ∪ towers ∪ places)
# grew past what Overpass finishes inside its kill-switch timeout, and a
# per-viewpoint cache made every new viewpoint pay full price again. Tiles
# are small (seconds each), retried individually, fetched with bounded
# concurrency (Overpass fair use: ~2 connections), and cached by tile — a
# nearby viewpoint reuses almost all of them. Failed tiles degrade to a
# `partial` response instead of a 502.
PEAKS_TILE_DEG = 0.5
# GLOBAL fetch discipline (not per request): at most OVERPASS_CONCURRENCY
# queries in flight against the instance across ALL clients (default 1 —
# fully serialized), one shared HTTP client, and an in-flight registry so
# two clients wanting the same tile share one fetch instead of racing it.
OVERPASS_CONCURRENCY = max(1, int(os.getenv("OVERPASS_CONCURRENCY", "1")))
# [timeout:N] is Overpass's SERVER-side budget for the query — generous, so
# a slow-but-progressing tile finishes instead of being killed and retried
# into the same wall (healthy tiles take ~1-3 s regardless). The HTTP client
# timeout must EXCEED it: giving up first abandons a query the server is
# still crunching — wasted work that still counts against per-IP quotas.
OVERPASS_TILE_TIMEOUT_S = int(os.getenv("OVERPASS_TILE_TIMEOUT_S", "60"))
_overpass_sem = asyncio.Semaphore(OVERPASS_CONCURRENCY)
_overpass_client: httpx.AsyncClient | None = None
_tile_cache: dict[tuple[float, float], tuple[float, list[dict]]] = {}
_tile_inflight: dict[tuple[float, float], "asyncio.Task[list[dict]]"] = {}

# the union body is the tile query's IDENTITY: it fingerprints the durable
# cache key, so editing the query (new feature kinds etc.) auto-invalidates
# stored tiles instead of mixing schemas
_TILE_UNION = (
    'node["natural"="peak"]["name"]({bbox});'
    'node["man_made"~"^(tower|mast)$"]'
    '["tower:type"~"^(observation|communication)$"]["name"]({bbox});'
    'node["place"~"^(city|town|village|suburb|quarter)$"]["name"]({bbox});')
_TILE_QUERY_FP = hashlib.md5(_TILE_UNION.encode()).hexdigest()[:8]


def _tile_db_key(t: tuple[float, float]) -> str:
    return f"{_TILE_QUERY_FP}:{t[0]:g}:{t[1]:g}"


async def _tile_db_get(t: tuple[float, float]) -> list[dict] | None:
    """L2: durable tile cache in the workbench DB (geocode_cache pattern) —
    survives the api reloads that wipe the in-process L1."""
    try:
        async with wb_engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT result, extract(epoch from now() - fetched_at) AS age "
                "FROM geocode_cache "
                "WHERE kind = 'overpass_tile' AND query = :q"),
                {"q": _tile_db_key(t)})).first()
        if row is not None and row.age < PEAKS_TTL_S and isinstance(row.result, list):
            return row.result
    except Exception as e:  # noqa: BLE001 — cache miss beats an error
        print(f"terrain peaks: tile db read failed: {e}", flush=True)
    return None


async def _tile_db_put(t: tuple[float, float], feats: list[dict]) -> None:
    try:
        async with wb_engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO geocode_cache (kind, query, result) "
                "VALUES ('overpass_tile', :q, CAST(:r AS jsonb)) "
                "ON CONFLICT (kind, query) DO UPDATE SET "
                "result = EXCLUDED.result, fetched_at = now()"),
                {"q": _tile_db_key(t), "r": json.dumps(feats)})
    except Exception as e:  # noqa: BLE001 — a lost cache write is harmless
        print(f"terrain peaks: tile db write failed: {e}", flush=True)


def _client() -> httpx.AsyncClient:
    global _overpass_client
    if _overpass_client is None:
        _overpass_client = httpx.AsyncClient(
            timeout=OVERPASS_TILE_TIMEOUT_S + 15,
            headers={"User-Agent": OVERPASS_UA})
    return _overpass_client


def parse_ele(v) -> float | None:
    """OSM ele/prominence values arrive as '1602', '1602.4', '1602 m', '1,602'…"""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None


def parse_pop(v) -> int | None:
    """OSM population arrives as '1324277', '1 324 277', '1,324,277'…"""
    if v is None:
        return None
    try:
        return int(float(str(v).replace(",", "").replace(" ", "").replace(" ", "")))
    except ValueError:
        return None


def features_from_overpass(data: dict) -> list[dict]:
    """Overpass JSON (peaks ∪ towers/masts ∪ places union) → candidate dicts.
    kind: peak | tower (observation) | mast (communication) | city | town |
    village | suburb | quarter. prominence rides along where OSM has it (~2%
    of peaks — but precisely the famous ones); population where places have
    it (~98% around Prague, probed 2026-07-28): the client uses both for
    label priority now that the pool is uncapped."""
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name, lat, lon = tags.get("name"), el.get("lat"), el.get("lon")
        if not name or lat is None or lon is None:
            continue
        if tags.get("place"):
            kind = tags["place"]
        elif tags.get("natural") == "peak":
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
        pop = parse_pop(tags.get("population"))
        if pop is not None:
            f["population"] = pop
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


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, la2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * math.asin(min(1.0, math.sqrt(a)))


def tiles_for(lat: float, lon: float, radius_m: float) -> list[tuple[float, float]]:
    """(south, west) corners of the fixed global grid tiles intersecting the
    radius disc — corner tiles whose NEAREST point is beyond it are skipped."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    out = []
    for ti in range(math.floor((lat - dlat) / PEAKS_TILE_DEG),
                    math.floor((lat + dlat) / PEAKS_TILE_DEG) + 1):
        for ui in range(math.floor((lon - dlon) / PEAKS_TILE_DEG),
                        math.floor((lon + dlon) / PEAKS_TILE_DEG) + 1):
            s, w = ti * PEAKS_TILE_DEG, ui * PEAKS_TILE_DEG
            near_lat = min(max(lat, s), s + PEAKS_TILE_DEG)
            near_lon = min(max(lon, w), w + PEAKS_TILE_DEG)
            if _haversine_m(lat, lon, near_lat, near_lon) <= radius_m:
                out.append((round(s, 4), round(w, 4)))
    return out


async def _fetch_tile(s: float, w: float) -> list[dict]:
    """One tile's candidates, with per-tile retries (transient Overpass load
    shedding is the norm, not the exception)."""
    bbox = f"{s},{w},{s + PEAKS_TILE_DEG},{w + PEAKS_TILE_DEG}"
    query = (f"[out:json][timeout:{OVERPASS_TILE_TIMEOUT_S}];("
             + _TILE_UNION.format(bbox=bbox) + ");out body;")
    last: Exception | None = None
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(0.5 * 4 ** (attempt - 1))  # 0.5 s, 2 s
        try:
            r = await _client().post(OVERPASS_URL, data={"data": query})
            r.raise_for_status()
            data = r.json()
            if data.get("remark"):
                raise RuntimeError(f"overpass aborted: {data['remark']}")
            return features_from_overpass(data)
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            last = e
    raise RuntimeError(f"tile {s},{w}: {last}")


async def _tile_task(t: tuple[float, float]) -> list[dict]:
    """THE single in-flight fetch for a tile — every concurrent requester
    awaits this one task. L2 (DB) first, Overpass only on a true miss,
    serialized by the global semaphore; caches to both layers on success."""
    feats = await _tile_db_get(t)
    if feats is None:
        async with _overpass_sem:
            feats = await _fetch_tile(*t)
        await _tile_db_put(t, feats)
    _tile_cache[t] = (time.monotonic(), feats)
    return feats


@router.get("/terrain/peaks")
async def peaks(lat: float, lon: float, radius_m: float = 100_000.0,
                chunk: int | None = None, chunks: int = 1):
    radius_m = max(1_000.0, min(radius_m, 200_000.0))
    tiles = tiles_for(lat, lon, radius_m)
    # chunked delivery (chunk=i&chunks=n): distance-sorted contiguous tile
    # slices, chunk 0 nearest — the client streams the pool near-first in
    # small, individually-retryable requests instead of one 45-s-fragile
    # monolith. No chunk param = the whole pool (old behavior).
    n_chunks = max(1, min(64, chunks))
    if chunk is not None:
        tiles.sort(key=lambda t: _haversine_m(
            lat, lon, t[0] + PEAKS_TILE_DEG / 2, t[1] + PEAKS_TILE_DEG / 2))
        i = max(0, min(chunk, n_chunks - 1))
        tiles = tiles[i * len(tiles) // n_chunks:(i + 1) * len(tiles) // n_chunks]
    now = time.monotonic()
    failed: list[tuple[float, float]] = []
    fetched = 0

    async def tile_feats(t: tuple[float, float]) -> list[dict]:
        nonlocal fetched
        hit = _tile_cache.get(t)
        if hit and now - hit[0] < PEAKS_TTL_S:
            return hit[1]
        # join the in-flight fetch if another request already started one
        task = _tile_inflight.get(t)
        if task is None or task.done():
            task = asyncio.create_task(_tile_task(t))
            _tile_inflight[t] = task
            task.add_done_callback(lambda _tk, key=t: _tile_inflight.pop(key, None))
            fetched += 1
        try:
            # shield: one client disconnecting must not cancel a fetch other
            # clients are awaiting (and the cache wants the result anyway)
            return await asyncio.shield(task)
        except Exception as e:  # noqa: BLE001 — degrade to stale/partial
            print(f"terrain peaks: {e}", flush=True)
            if hit:  # a stale tile beats a hole in the pool
                return hit[1]
            failed.append(t)
            return []

    per_tile = await asyncio.gather(*(tile_feats(t) for t in tiles))
    if failed and len(failed) == len(tiles):
        raise HTTPException(502, "overpass: all candidate tiles failed")

    # assemble: dedupe tile-boundary nodes (Overpass bboxes are inclusive),
    # then cut the square union back to the requested disc
    seen: set[tuple] = set()
    result: list[dict] = []
    for feats in per_tile:
        for f in feats:
            k = (f["name"], f["lat"], f["lon"])
            if k in seen:
                continue
            seen.add(k)
            if _haversine_m(lat, lon, f["lat"], f["lon"]) <= radius_m:
                result.append(f)
    from starlette.concurrency import run_in_threadpool
    # mutates the cached dicts in place — the DEM fill sticks per tile, so
    # later requests over the same tiles skip the resampling too
    await run_in_threadpool(fill_missing_ele, result)
    result.sort(key=lambda p: p["ele"] if p["ele"] is not None else -math.inf,
                reverse=True)
    out = {"peaks": result, "tiles": len(tiles), "fetched": fetched}
    if chunk is not None:
        out["chunk"], out["chunks"] = chunk, n_chunks
    if failed:
        out["partial"] = True
        out["failed_tiles"] = len(failed)
    return out


# ---------------------------------------------------------------------------
# overlay fit: the /terrain/overlay bench's manual pano↔render alignment,
# saved as ONE content-addressed fact (hv:terrainOverlayFit, canonical-JSON
# literal) about the photo — same run/curation plumbing as calibrate accept.
# The fit is pure image-intrinsic geometry (projection, absolute centre
# bearing, fov, horizon %, vertical scale, roll, piecewise warp in degrees);
# which render it was fitted against is provenance and lives in run params.
# ---------------------------------------------------------------------------

class OverlayFitRequest(BaseModel):
    photo_id: str
    render_id: str | None = None
    projection: str                  # equirect | cylindrical | rectilinear
    centre_bearing: float            # absolute, degrees
    fov_deg: float
    horizon_pct: float               # horizon line, % of image height
    v_scale: float                   # vertical trim × the square-pixel guess
    roll_deg: float
    warp: list[float] = []           # per-handle offsets, degrees, left→right
    # horizontal (azimuth) warp on the same handles, degrees: absorbs the
    # local stretch a stitched pano carries between seams. Optional; a fit
    # without one (or all zeros) is serialised WITHOUT the key, so fits saved
    # before the field existed keep their canonical JSON (= stay "landed")
    hwarp: list[float] | None = None
    # per-panel SCALE (about the panel's centre, both axes — a frame stitched
    # at the wrong focal length) and the handle positions as width fractions
    # (seams placed by hand). Both optional; serialised only when non-neutral
    hscale: list[float] | None = None
    knots: list[float] | None = None
    # atmospheric visibility read off the photo (fog slider), km; null = full
    visibility_km: float | None = None
    # client wall-clock (epoch ms) of the change — DRAFTS ONLY, so a browser
    # can tell its stale local live-state from a fresher draft written by
    # another browser; facts stay timestamp-free (content-addressed)
    saved_at: float | None = None
    note: str | None = None


def _overlay_fit_json(req: OverlayFitRequest, with_ts: bool = False) -> str:
    fit = {"projection": req.projection,
           "centre_bearing": round(req.centre_bearing, 3),
           "fov_deg": round(req.fov_deg, 3),
           "horizon_pct": round(req.horizon_pct, 3),
           "v_scale": round(req.v_scale, 4),
           "roll_deg": round(req.roll_deg, 3),
           "warp": [round(w, 4) for w in req.warp],
           "visibility_km": (round(req.visibility_km, 1)
                             if req.visibility_km is not None else None)}
    if req.hwarp and any(abs(w) > 0 for w in req.hwarp):
        fit["hwarp"] = [round(w, 4) for w in req.hwarp]
    if req.hscale and any(abs(v - 1.0) > 1e-9 for v in req.hscale[:-1]):
        fit["hscale"] = [round(v, 5) for v in req.hscale]
    if req.knots and len(req.knots) >= 2:
        n = len(req.knots)
        if any(abs(k - i / (n - 1)) > 1e-6 for i, k in enumerate(req.knots)):
            fit["knots"] = [round(k, 5) for k in req.knots]
    if with_ts and req.saved_at is not None:
        fit["saved_at"] = round(req.saved_at)
    return json.dumps(fit, sort_keys=True, separators=(",", ":"))


@router.post("/terrain/overlay-fit")
async def save_overlay_fit(req: OverlayFitRequest):
    from .. import facts, graph
    from ..runs import create_run, fail_run, finish_run
    if req.projection not in ("equirect", "cylindrical", "rectilinear"):
        raise HTTPException(422, "unknown projection")
    fit_json = _overlay_fit_json(req)
    run_id = await create_run(
        kind="overlay_fit",
        params={"photo_id": req.photo_id, "render_id": req.render_id,
                "fit": json.loads(fit_json)},
        note=req.note)
    try:
        ph = facts.iri(graph.photo_iri(req.photo_id))
        s, p, o = ph, facts._p("terrainOverlayFit"), facts.lit(fit_json)
        g = graph.fact_iri(facts.fact_hash(s, p, o))
        await graph.store.load_turtle(g, f"{s} {p} {o} .\n")
        run = facts.iri(graph.run_iri(run_id))
        meta = (f"{facts.iri(g)} <http://www.w3.org/ns/prov#wasGeneratedBy> {run} .\n"
                f"{facts.iri(g)} {facts._p('about')} {ph} .")
        await graph.store.load_turtle(graph.GRAPH_META,
                                      graph.PREFIXES + "\n" + meta)
        await finish_run(run_id, stats={"facts": 1},
                         graph_iri=graph.run_iri(run_id))
        return {"run_id": str(run_id), "fact": g}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"overlay fit save failed: {e}")


@router.get("/terrain/overlay-fit")
async def get_overlay_fit(photo_id: str):
    """Newest non-rejected saved fit for the photo (approved beats newer,
    mirroring the calibration pick)."""
    from .. import graph
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?f ?v ?run ?status WHERE {{
  GRAPH ?f {{ <{graph.photo_iri(photo_id)}> hv:terrainOverlayFit ?v }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_META}> {{ ?f prov:wasGeneratedBy ?run }} }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    cands = []
    for b in res["results"]["bindings"]:
        status = b.get("status", {}).get("value", "")
        if status.endswith("rejected"):
            continue
        cands.append({"fact": b["f"]["value"],
                      "run": b.get("run", {}).get("value", ""),
                      "approved": status.endswith("approved"),
                      "value": b["v"]["value"]})
    if not cands:
        return {"fit": None}
    order: dict[str, int] = {}
    run_ids = [c["run"].rsplit("/", 1)[-1] for c in cands if c["run"]]
    if run_ids:
        async with wb_engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id FROM runs WHERE id = ANY(CAST(:ids AS uuid[])) "
                "ORDER BY started_at"), {"ids": run_ids})).all()
        for i, (rid,) in enumerate(rows):
            order[str(rid)] = i
    best = max(cands, key=lambda c: (c["approved"],
                                     order.get(c["run"].rsplit("/", 1)[-1], -1)))
    try:
        fit = json.loads(best["value"])
    except ValueError:
        return {"fit": None}
    # `fact` is what the bench curates: approving THIS fit is what marks the
    # overlay for graduation (docs/terrain-overlay-graduation.md — approval is
    # the selection, there is no separate marked-for-export flag)
    return {"fit": fit, "fact": best["fact"],
            "run_id": best["run"].rsplit("/", 1)[-1] or None,
            "approved": best["approved"]}


class OverlayGraduateRequest(BaseModel):
    photo_id: str
    fact: str
    graduate: bool
    note: str | None = None


@router.post("/terrain/overlay-fit/graduate")
async def graduate_overlay_fit(req: OverlayGraduateRequest):
    """Mark (or unmark) a saved fit for graduation into the main app.

    Graduation has no flag of its own — approving the fit fact IS the
    selection, the same way the /graduation review is the selection for
    annotation ops. What this adds over a plain POST /facts/curate is the
    ONE-APPROVED-FIT-PER-PHOTO invariant: approving a re-fit demotes the
    previous one to proposed, so the exporter never has to choose between
    two approved alignments of the same photo. Un-graduating clears the
    decision (proposed), which is NOT the same as rejecting — a rejected
    fit is a bad fit, an unapproved one is merely not published yet.
    """
    import datetime

    from .. import facts, graph
    if not req.fact.startswith(graph.BASE + "/id/fact/"):
        raise HTTPException(422, f"not a fact-graph IRI: {req.fact}")
    ph = graph.photo_iri(req.photo_id)
    # the fact must really be an overlay fit ABOUT this photo: curation is
    # keyed only by graph IRI, so an unchecked id would happily approve
    # something else entirely
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?f ?status WHERE {{
  GRAPH ?f {{ <{ph}> hv:terrainOverlayFit ?v }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    known = {b["f"]["value"]: b.get("status", {}).get("value", "")
             for b in res["results"]["bindings"]}
    if req.fact not in known:
        raise HTTPException(404, "no such overlay fit for this photo")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if req.graduate:
        await graph.store.update(facts.curate_update(
            req.fact, "approved", decided_at_iso=now, note=req.note))
        # demote only the previously APPROVED siblings — a rejected fit is a
        # judgement about that alignment and must survive untouched
        for other, status in known.items():
            if other != req.fact and status.endswith("approved"):
                await graph.store.update(facts.curate_update(
                    other, "proposed", decided_at_iso=now,
                    note="superseded by a newer graduated fit"))
    else:
        await graph.store.update(facts.curate_update(
            req.fact, "proposed", decided_at_iso=now, note=req.note))
    return {"fact": req.fact, "graduated": req.graduate, "decided_at": now}


# ---------------------------------------------------------------------------
# overlay draft: the bench's intermediate alignment state, auto-saved — same
# mutable-RDF pattern as the calibration draft (one JSON literal in a
# per-photo draft graph, replaced wholesale; NOT a content-addressed fact).
# Promoting to a fact via POST /terrain/overlay-fit clears it client-side.
# ---------------------------------------------------------------------------

def _overlay_draft_graph(photo_id: str) -> str:
    from .. import graph
    return f"{graph.BASE}/id/graph/draft/overlay/{photo_id}"


@router.get("/terrain/overlay-draft")
async def get_overlay_draft(photo_id: str):
    from .. import graph
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?v WHERE {{
  GRAPH <{_overlay_draft_graph(photo_id)}> {{
    <{graph.photo_iri(photo_id)}> hv:terrainOverlayDraft ?v }}
}}""")
    b = res["results"]["bindings"]
    if not b:
        return {"draft": None}
    try:
        return {"draft": json.loads(b[0]["v"]["value"])}
    except ValueError:
        return {"draft": None}


@router.put("/terrain/overlay-draft")
async def put_overlay_draft(req: OverlayFitRequest):
    from .. import facts, graph
    g = _overlay_draft_graph(req.photo_id)
    fit_json = _overlay_fit_json(req, with_ts=True)
    await graph.store.update(f"DROP SILENT GRAPH <{g}>")
    ph = facts.iri(graph.photo_iri(req.photo_id))
    await graph.store.load_turtle(
        g, f"{ph} {facts._p('terrainOverlayDraft')} {facts.lit(fit_json)} .\n")
    return {"draft": json.loads(fit_json)}


@router.delete("/terrain/overlay-draft")
async def delete_overlay_draft(photo_id: str):
    from .. import graph
    await graph.store.update(
        f"DROP SILENT GRAPH <{_overlay_draft_graph(photo_id)}>")
    return {"draft": None}


# ---------------------------------------------------------------------------
# client phone-home debug log: the overlay page batches its debug lines here
# so MOBILE sessions are inspectable without tethered devtools. Kept in an
# in-memory ring (GET) and echoed to stdout (docker logs enrich_api).
# ---------------------------------------------------------------------------

from collections import deque as _deque

_client_log: "_deque[dict]" = _deque(maxlen=800)


class ClientLogRequest(BaseModel):
    session: str
    page: str
    ua: str | None = None
    messages: list[dict]


@router.post("/terrain/client-log")
async def client_log(req: ClientLogRequest):
    now = time.strftime("%H:%M:%S")
    for m in req.messages[:100]:
        entry = {"at": now, "session": str(req.session)[:16],
                 "page": str(req.page)[:120], "ua": (req.ua or "")[:180],
                 "t": str(m.get("t", ""))[:16],
                 "msg": str(m.get("msg", ""))[:600]}
        _client_log.append(entry)
        print(f"client-log [{entry['session'][:6]}] {entry['t']} {entry['msg']}",
              flush=True)
    return {"ok": len(req.messages)}


@router.get("/terrain/client-log")
async def client_log_read(n: int = 200, session: str | None = None):
    items = [e for e in _client_log
             if not session or e["session"].startswith(session)]
    return {"entries": items[-max(1, min(n, 800)):]}
