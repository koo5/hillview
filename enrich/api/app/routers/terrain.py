"""Terrain bench API: enqueue depth-panorama renders for photo viewpoints
(or ad-hoc lat/lon), receive worker results, and serve the artifacts the
bench viewer needs (raw uint16 depth buffer + preview JPEG + meta)."""
import json
import os

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text

from .. import config
from ..db import wb_engine

router = APIRouter()

WORKER_TOKEN = os.getenv("ENRICH_WORKER_TOKEN", "dev-worker-token")
CALLBACK_BASE = os.getenv("WORKER_CALLBACK_BASE", "http://127.0.0.1:8070")

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
    actors.render_panorama.send({
        "result_id": str(rid), "lat": lat, "lon": lon, "params": params,
        "callback": f"{CALLBACK_BASE}/api/terrain/result",
        "token": WORKER_TOKEN,
    })
    return {"queued": str(rid)}


@router.post("/terrain/result")
async def result(result_json: str = Form(...),
                 depth: UploadFile | None = File(None),
                 preview: UploadFile | None = File(None),
                 x_worker_token: str = Header(None)):
    if x_worker_token != WORKER_TOKEN:
        raise HTTPException(403, "bad worker token")
    d = json.loads(result_json)
    rid = d["result_id"]

    if d.get("status") == "rendering":
        # Progress ping (tiny JSON, no artifacts): % rides in the meta jsonb
        # until the final result overwrites it. The status guard keeps an
        # out-of-order late ping from regressing a finished/failed render.
        async with wb_engine.begin() as conn:
            await conn.execute(text(
                "UPDATE terrain_renders SET status = 'rendering', "
                "meta = CAST(:meta AS jsonb), worker = :w "
                "WHERE id = CAST(:id AS uuid) AND status NOT IN ('done', 'error')"),
                {"meta": json.dumps(d.get("meta")), "w": d.get("worker"), "id": rid})
        return {"ok": True}

    tdir = os.path.join(config.ARTIFACTS_DIR, "terrain")
    os.makedirs(tdir, exist_ok=True)
    depth_path = preview_path = None
    if depth is not None:
        depth_path = os.path.join("terrain", f"{rid}.depth.bin")
        with open(os.path.join(config.ARTIFACTS_DIR, depth_path), "wb") as f:
            f.write(await depth.read())
    if preview is not None:
        preview_path = os.path.join("terrain", f"{rid}.preview.jpg")
        with open(os.path.join(config.ARTIFACTS_DIR, preview_path), "wb") as f:
            f.write(await preview.read())
    async with wb_engine.begin() as conn:
        await conn.execute(text(
            "UPDATE terrain_renders SET status = :st, error = :err, "
            "meta = CAST(:meta AS jsonb), depth_path = :dp, preview_path = :pp, "
            "worker = :w, finished_at = now() WHERE id = CAST(:id AS uuid)"),
            {"st": d.get("status", "done"), "err": d.get("error"),
             "meta": json.dumps(d.get("meta")) if d.get("meta") else None,
             "dp": depth_path, "pp": preview_path, "w": d.get("worker"), "id": rid})
    return {"ok": True}


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
    return {"renders": [dict(r) | {"id": str(r["id"])} for r in rows]}


async def _artifact(render_id: str, col: str) -> str:
    async with wb_engine.connect() as conn:
        path = (await conn.execute(text(
            f"SELECT {col} FROM terrain_renders WHERE id = CAST(:id AS uuid)"),
            {"id": render_id})).scalar()
    if not path:
        raise HTTPException(404, "artifact not available")
    return os.path.join(config.ARTIFACTS_DIR, path)


@router.get("/terrain/renders/{render_id}/depth")
async def depth_artifact(render_id: str):
    return FileResponse(await _artifact(render_id, "depth_path"),
                        media_type="application/octet-stream")


@router.get("/terrain/renders/{render_id}/preview")
async def preview_artifact(render_id: str):
    return FileResponse(await _artifact(render_id, "preview_path"),
                        media_type="image/jpeg")
