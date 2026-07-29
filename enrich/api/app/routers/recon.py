"""Recon bench API: browse MASt3R-SfM reconstructions and their structure metrics.

Read-only for now — running new reconstructions from the bench is the next bite. What
this serves is the seven archived runs plus whatever the queue produces later, with the
metrics that actually say whether a solve is good:

  * reprojection error in px (the structure metric — depth and pose together)
  * epipolar distance in px (a cheap screen, blind along its own epipolar lines)
  * the camera<->GPS residual, which is a DRIFT GATE and ranks these runs with a
    Spearman correlation of 0.07 against structure; it is displayed to be disagreed with.

See scripts/enrich/recon_metrics.py and docs/reconstruction-field-notes.md. The per-pair
table lives in the metrics.json artifact rather than the DB column: it is the
false-link/Doppelganger view and can reach a quarter-megabyte, so it is fetched per run
rather than on every list.
"""
import datetime
import json
import os
import shutil
import tempfile
import time
import uuid

from fastapi import (APIRouter, File, Form, Header, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text

from .. import config
from ..db import wb_engine

router = APIRouter()

WORKER_TOKEN = os.getenv("ENRICH_WORKER_TOKEN", "dev-worker-token")

# reconstruct.py flags a client may set. Selection knobs (radius/n/stride/window) are
# handled by the API instead — the worker gets an explicit frame manifest — so what is
# left here is solver and masking behaviour. Mirrored in the worker (defense both ends).
ALLOWED_PARAMS = {"win", "pairs", "pair_dist", "pair_dang", "size",
                  "niter1", "niter2", "dense", "min_conf",
                  "mask_anon", "mask_solocator", "shared_intrinsics"}

# Where the archived experiment runs live. Import copies out of here; nothing writes to it.
ARCHIVE_ROOT = os.getenv(
    "RECON_ARCHIVE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "..", "..", "scripts", "enrich", "runs"))

# The sparse layer worth keeping: poses/points/metrics/renders, ~16 MB per run. The
# forward-pass cache (1.8-2.7 GB) is deliberately NOT copied — it is regenerable and
# only needed to re-solve.
ARTIFACT_FILES = {
    "metadata_path": "metadata.json",
    "metrics_path": "metrics.json",
    "cloud_path": "points.ply",
    "topdown_path": "topdown.png",
    "pairs_matrix_path": "pairs_matrix.png",
}

# Summary columns lifted out of metrics.json into the `metrics` jsonb, so listing does
# not touch the artifacts. Keys mirror recon_metrics.measure()'s output.
SUMMARY_KEYS = ("reproj_px", "epipolar_px", "reproj_px_median_of_pairs",
                "epipolar_px_median_of_pairs", "reproj_coverage", "n_behind_camera",
                "gps_residual_m", "gps_residual_archived_m", "gps_residual_informative",
                "pp_source", "pose_source", "depth_source", "loaded_size",
                "reproduced_archived_solve", "resolve_vs_archived",
                "n_degenerate_baseline_pairs", "scale_units_per_m",
                # Doppelganger control: the verdict and the real-only baseline it is
                # judged against have to survive into the row, or the bench can only
                # show it by re-reading the artifact.
                "n_injected", "real_only_reproj_px", "real_only_epipolar_px",
                "impostors",
                # how far this cluster's baseline can actually constrain depth
                "depth_horizon")


def _artifact_abspath(rel: str) -> str:
    """Resolve an artifact-relative path under ARTIFACTS_DIR, refusing anything that
    escapes it (symlinks included) — same guard as the terrain bench uses."""
    root = os.path.realpath(config.ARTIFACTS_DIR)
    full = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([root, full]) != root:
        raise HTTPException(400, "artifact path escapes the artifacts dir")
    return full


def _summary(metrics: dict) -> dict:
    return {k: metrics[k] for k in SUMMARY_KEYS if k in metrics}


@router.get("/recon/runs")
async def list_runs(limit: int = 100):
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, name, source, status, error, n_frames, n_pairs, captured_on, "
            "params, metrics, meta, "
            "cloud_path IS NOT NULL AS has_cloud, "
            "topdown_path IS NOT NULL AS has_topdown, "
            "pairs_matrix_path IS NOT NULL AS has_pairs_matrix, "
            "metrics_path IS NOT NULL AS has_metrics, "
            "worker, enqueued_at, finished_at "
            "FROM recon_runs ORDER BY enqueued_at DESC, name LIMIT :lim"),
            {"lim": min(limit, 500)})).mappings().all()
    return {"runs": [dict(r) | {"id": str(r["id"])} for r in rows],
            "queue": await _queue_state()}


@router.get("/recon/runs/{run_id}")
async def get_run(run_id: str):
    """One run, with the per-frame table and the per-pair errors read from the artifact.

    The pair list is the point of the detail view: a run-level median hides the tail,
    and a false link shows up as one pair disagreeing with an otherwise coherent solve.
    """
    try:
        rid = str(uuid.UUID(run_id))
    except ValueError:
        raise HTTPException(400, "run_id is not a uuid")
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT * FROM recon_runs WHERE id = CAST(:id AS uuid)"),
            {"id": rid})).mappings().first()
    if not row:
        raise HTTPException(404, "run not found")
    # same has_* booleans the list query computes, so the page can use one shape for both
    out = dict(row) | {"id": str(row["id"])} | {
        "has_cloud": bool(row["cloud_path"]),
        "has_topdown": bool(row["topdown_path"]),
        "has_pairs_matrix": bool(row["pairs_matrix_path"]),
        "has_metrics": bool(row["metrics_path"]),
        "has_log": bool(row["log_path"]),
    }

    frames, pairs, worst = [], [], []
    if row["metrics_path"]:
        try:
            with open(_artifact_abspath(row["metrics_path"])) as f:
                m = json.load(f)
            frames, pairs, worst = (m.get("frames") or [], m.get("pairs") or [],
                                   m.get("worst_pairs") or [])
        except (OSError, json.JSONDecodeError) as e:
            out["artifact_error"] = f"{type(e).__name__}: {e}"
    # geometry for the track map comes from metadata.json (GPS + recovered per frame)
    geo = None
    if row["metadata_path"]:
        try:
            with open(_artifact_abspath(row["metadata_path"])) as f:
                md = json.load(f)
            by_idx = {fr["idx"]: fr for fr in (md.get("frames") or [])}
            geo = {"center": md.get("center"),
                   "frames": [{"idx": i,
                               "id": by_idx[i].get("id"),
                               "captured_at": by_idx[i].get("captured_at"),
                               "gps": by_idx[i].get("gps"),
                               "recovered_gps": by_idx[i].get("recovered_gps"),
                               "focal_px": by_idx[i].get("focal_px")}
                              for i in sorted(by_idx)]}
        except (OSError, json.JSONDecodeError, KeyError):
            geo = None
    out["frames"] = frames
    out["pairs"] = pairs
    out["worst_pairs"] = worst
    out["geo"] = geo
    return out


async def _artifact(run_id: str, col: str) -> str:
    if col not in ARTIFACT_FILES and col != "log_path":
        raise HTTPException(400, "unknown artifact")
    try:
        rid = str(uuid.UUID(run_id))
    except ValueError:
        raise HTTPException(400, "run_id is not a uuid")
    async with wb_engine.connect() as conn:
        path = (await conn.execute(text(
            f"SELECT {col} FROM recon_runs WHERE id = CAST(:id AS uuid)"),
            {"id": rid})).scalar()
    if not path:
        raise HTTPException(404, "artifact not available")
    return _artifact_abspath(path)


@router.get("/recon/runs/{run_id}/cloud")
async def cloud_artifact(run_id: str, request: Request):
    """The sparse point cloud (.ply). Text PLY compresses ~4:1, so negotiate gzip —
    walk_jizni's is 34 MB raw and this is the practical limit on serving it at all."""
    path = await _artifact(run_id, "cloud_path")
    gz = path + ".gz"
    if "gzip" in request.headers.get("accept-encoding", "") and os.path.exists(gz):
        return FileResponse(gz, media_type="application/octet-stream",
                            headers={"Content-Encoding": "gzip",
                                     "Vary": "Accept-Encoding"})
    return FileResponse(path, media_type="application/octet-stream")


def _ply_to_packed(ply_path: str, max_points: int) -> bytes:
    """ASCII PLY -> packed little-endian [float32 x,y,z][uint8 r,g,b] per point.

    The viewer cannot eat the PLY directly at these sizes: reconstruct.py writes ASCII, so
    a 700 k-point sparse cloud is ~65 MB and a dense one runs to hundreds. Packed, a point
    costs 15 bytes instead of ~90, and gzip takes it further. Points beyond max_points are
    dropped by even stride rather than truncation, so a downsampled cloud still covers the
    whole scene instead of half of it.
    """
    import struct
    header, pts = True, []
    n_declared = 0
    with open(ply_path) as f:
        for line in f:
            if header:
                if line.startswith("element vertex"):
                    n_declared = int(line.split()[-1])
                elif line.startswith("end_header"):
                    header = False
                continue
            pts.append(line)
    n = n_declared or len(pts)
    # ceil, not floor: floor(715532/400000) == 1 leaves the cap unenforced
    step = max(1, -(-n // max_points)) if max_points else 1
    out = bytearray()
    for i in range(0, len(pts), step):
        p = pts[i].split()
        if len(p) < 6:
            continue
        out += struct.pack("<fff3B", float(p[0]), float(p[1]), float(p[2]),
                           int(float(p[3])), int(float(p[4])), int(float(p[5])))
    return bytes(out)


@router.get("/recon/runs/{run_id}/cloud.bin")
async def cloud_packed(run_id: str, request: Request, max_points: int = 1_500_000,
                       dense: bool = False):
    """The point cloud in the viewer's format, converted on first request and cached.

    Cached beside the artifact because the conversion is a full parse of a many-megabyte
    text file — fine once, not per page load.
    """
    col = "cloud_path"
    path = await _artifact(run_id, col)
    src = path
    if dense:
        cand = os.path.join(os.path.dirname(path), "dense.ply")
        if os.path.exists(cand):
            src = cand
    cache = f"{src}.{max_points}.bin"
    if not os.path.exists(cache):
        _write_atomic(cache, _ply_to_packed(src, max_points))
    return FileResponse(cache, media_type="application/octet-stream",
                        headers={"X-Point-Stride": "15"})


@router.get("/recon/runs/{run_id}/cameras")
async def cameras(run_id: str):
    """Camera poses + focals for drawing frusta, straight from metadata.json.

    scene.npz is not uploaded, but metadata.json carries pose_cam2world and focal_px per
    frame, which is everything a frustum needs.
    """
    path = await _artifact(run_id, "metadata_path")
    with open(path) as f:
        md = json.load(f)
    return {"frames": [{"idx": fr["idx"], "id": fr.get("id"),
                        "pose": fr.get("pose_cam2world"),
                        "focal_px": fr.get("focal_px"),
                        "injected": bool(fr.get("injected"))}
                       for fr in (md.get("frames") or [])
                       if fr.get("pose_cam2world")]}


@router.get("/recon/runs/{run_id}/topdown")
async def topdown_artifact(run_id: str):
    return FileResponse(await _artifact(run_id, "topdown_path"), media_type="image/png")


@router.get("/recon/runs/{run_id}/pairs_matrix")
async def pairs_matrix_artifact(run_id: str):
    return FileResponse(await _artifact(run_id, "pairs_matrix_path"),
                        media_type="image/png")


class EnqueueRequest(BaseModel):
    name: str | None = None          # run label; defaults to a timestamped one
    lat: float                       # cluster centre
    lon: float
    radius_m: float = 300
    limit: int = 24                  # frames to keep after ordering by capture time
    offset: int = 0
    stride: int = 1                  # 1 = every frame. NEVER subsample a sweep: at ~14 m
                                     # spacing the solve collapsed (81 m drift) — the
                                     # bench exposes it only to reproduce that control.
    after: str | None = None         # capture-time window, 'YYYY-MM-DD HH:MM:SS'
    before: str | None = None
    inject: list[str] = []           # photo ids to add as impostors (Doppelganger test)
    params: dict = {}


def _ts(v: str | None, field: str) -> datetime.datetime | None:
    """asyncpg binds before any cast, so a timestamp parameter must be a real datetime.
    Accepts 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS[.ffffff]'."""
    if not v:
        return None
    try:
        return datetime.datetime.fromisoformat(v)
    except ValueError:
        raise HTTPException(422, f"{field}: expected an ISO timestamp, got {v!r}")


async def _select_frames(req: EnqueueRequest) -> list[dict]:
    """The cluster, chosen from the live mirror.

    Selection lives here rather than in reconstruct.py's dump-CSV scan so a run records
    the frames it actually used, and so the worker needs no DB credentials. Gates mirror
    select_cluster's: completed, not deleted, still present upstream, positioned, and
    with a full-res URL to download. Ordered by capture time because index-based
    selection silently mixed months in the June experiments.
    """
    sql = (
        "SELECT id, ST_Y(geometry) AS lat, ST_X(geometry) AS lon, altitude, "
        "  compass_angle, captured_at, title, width, height, original_filename, "
        "  detected_objects, owner_id, client_public_key_id, "
        "  exif_data->'data' AS exif, sizes->'full'->>'url' AS full_url "
        "FROM photo_mirror "
        "WHERE deleted = false AND missing_since IS NULL "
        "  AND processing_status = 'completed' "
        "  AND geometry IS NOT NULL AND sizes->'full'->>'url' IS NOT NULL "
        "  AND ST_DWithin(geometry::geography, "
        "      ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :rad) "
        # cast before the NULL test: a bare parameter there is an untypeable
        # AmbiguousParameterError to postgres
        "  AND (CAST(:after AS timestamp) IS NULL "
        "       OR captured_at >= CAST(:after AS timestamp)) "
        "  AND (CAST(:before AS timestamp) IS NULL "
        "       OR captured_at <= CAST(:before AS timestamp)) "
        "ORDER BY captured_at, id")
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(sql), {
            "lon": req.lon, "lat": req.lat, "rad": req.radius_m,
            "after": _ts(req.after, "after"),
            "before": _ts(req.before, "before")})).mappings().all()
        picked = list(rows)[req.offset::max(1, req.stride)][:max(0, req.limit)]
        frames = [_manifest_frame(r) for r in picked]
        if req.inject:
            inj = (await conn.execute(text(
                "SELECT id, ST_Y(geometry) AS lat, ST_X(geometry) AS lon, altitude, "
                "  compass_angle, captured_at, title, width, height, "
                "  original_filename, detected_objects, owner_id, "
                "  client_public_key_id, exif_data->'data' AS exif, "
                "  sizes->'full'->>'url' AS full_url "
                "FROM photo_mirror WHERE id = ANY(:ids) "
                "  AND geometry IS NOT NULL AND sizes->'full'->>'url' IS NOT NULL"),
                {"ids": req.inject})).mappings().all()
            # impostors are excluded from the GPS alignment fit downstream, so they
            # cannot drag the similarity transform toward themselves
            frames += [_manifest_frame(r) | {"injected": True} for r in inj]
    return frames


BLUR_CONFIDENCE = 0.4   # mirrors backend/worker/detections.py should_blur()


def _anon_boxes(detected: object) -> list[list[float]]:
    """Boxes that were actually blurred, in ORIGINAL image px — for correspondence
    masking (never painted; a fill would add features at box edges)."""
    if isinstance(detected, str):
        try:
            detected = json.loads(detected)
        except json.JSONDecodeError:
            return []
    out = []
    for o in ((detected or {}).get("objects") or []):
        b = o.get("bbox") or {}
        if not all(k in b for k in ("x1", "y1", "x2", "y2")):
            continue
        conf = o.get("confidence")
        if o.get("blurred", conf is None or conf >= BLUR_CONFIDENCE):
            out.append([b["x1"], b["y1"], b["x2"], b["y2"]])
    return out


def _camera_id(exif: dict | None, client_key, owner_id, w, h) -> str:
    """Which camera took this. Three tiers, best first:

      1. EXIF Make/Model/LensModel — authoritative, but present on only ~12% of the mirror
         because the app re-encodes its own uploads and strips camera tags.
      2. client_public_key_id — the uploading device's key fingerprint, 100% populated in
         production and genuinely per-DEVICE. The right signal for app photos; owner alone
         is not, since one account can upload from several phones.
      3. owner — the fallback for rows mirrored before the key column existed.

    Deliberately NOT including frame size: that is a separate axis (see _uniform_capture).
    """
    e = exif or {}
    parts = [str(e.get(k) or "").strip() for k in ("Make", "Model", "LensModel")]
    if any(parts):
        return "exif:" + "|".join(parts)
    if client_key:
        return f"client:{client_key}"
    return f"owner:{owner_id}"


def _rel_bucket(v, pct: float = 2.0) -> str:
    """Bucket a positive number to within `pct` percent, so near-equal values collapse."""
    import math
    if not v or v <= 0:
        return "?"
    return str(round(math.log(v) / math.log(1 + pct / 100.0)))


def _f35(exif: dict) -> float | None:
    raw = exif.get("FocalLength35efl") or exif.get("FocalLengthIn35mmFormat")
    if raw is None:
        return None
    try:
        return float(str(raw).split()[0].rstrip("mm"))
    except (TypeError, ValueError):
        return None


def _exif_focal_px(exif: dict | None, long_side_px: int) -> float | None:
    """Focal in pixels of a frame whose long side is `long_side_px`, from EXIF's 35 mm
    equivalent. The 35 mm frame's long side is 36 mm, so f_px = f35 * long_side / 36.

    This is the real answer where it exists: no need to solve for a parameter the camera
    already wrote down. FocalLength35efl is present on ~4.8 k photos (the DSLR uploads).
    """
    f35 = _f35(exif or {})
    # rounded to whole pixels: EXIF's 13-decimal zoom precision is not real accuracy, and
    # sub-pixel differences would make an otherwise-uniform cluster look inconsistent
    return round(f35 * long_side_px / 36.0) if f35 and f35 > 0 else None


def _manifest_frame(r) -> dict:
    cap = r["captured_at"]
    return {
        "id": str(r["id"]),
        "lat": float(r["lat"]), "lon": float(r["lon"]),
        "altitude": float(r["altitude"]) if r["altitude"] is not None else None,
        "compass_angle": (float(r["compass_angle"])
                          if r["compass_angle"] is not None else None),
        "captured_at": cap.strftime("%Y-%m-%d %H:%M:%S.%f") if cap else "",
        "full_url": r["full_url"],
        "width": int(r["width"] or 0), "height": int(r["height"] or 0),
        "title": r["title"] or "",
        "original_filename": r["original_filename"] or "",
        "anon_boxes": _anon_boxes(r["detected_objects"]),
        "owner_id": str(r["owner_id"]) if r["owner_id"] else None,
        "camera": _camera_id(r["exif"], r["client_public_key_id"], r["owner_id"],
                             r["width"], r["height"]),
        # the focal the camera itself recorded, in pixels of the 512-long-side frame the
        # solver works on — ground truth wherever EXIF survived
        "exif_focal_px_512": _exif_focal_px(r["exif"], 512),
    }


@router.post("/recon/runs")
async def enqueue(req: EnqueueRequest):
    from .. import actors
    if not actors.init_broker():
        raise HTTPException(503, "no RABBITMQ_URL configured")
    params = {k: v for k, v in (req.params or {}).items() if k in ALLOWED_PARAMS}
    frames = await _select_frames(req)
    if len(frames) < 2:
        raise HTTPException(422, f"selected {len(frames)} frame(s); need >= 2")

    name = req.name or f"bench-{time.strftime('%Y%m%d-%H%M%S')}"
    caps = sorted(f["captured_at"][:10] for f in frames if f.get("captured_at"))
    try:
        captured = datetime.date.fromisoformat(caps[0]) if caps else None
    except ValueError:
        captured = None
    spec = {"center": [req.lat, req.lon], "radius_m": req.radius_m,
            "limit": req.limit, "offset": req.offset, "stride": req.stride,
            "after": req.after, "before": req.before, "inject": req.inject,
            "params": params}

    async with wb_engine.begin() as conn:
        rid = (await conn.execute(text(
            "INSERT INTO recon_runs (name, source, params, status, n_frames, "
            "  captured_on, meta) "
            "VALUES (:name, 'bench', CAST(:params AS jsonb), 'queued', :nf, "
            "  CAST(:cap AS date), CAST(:meta AS jsonb)) "
            "ON CONFLICT (name, source) DO UPDATE SET "
            "  params = EXCLUDED.params, status = 'queued', error = NULL, "
            "  n_frames = EXCLUDED.n_frames, captured_on = EXCLUDED.captured_on, "
            "  meta = EXCLUDED.meta, metrics = NULL, enqueued_at = now(), "
            "  finished_at = NULL "
            "RETURNING id"),
            {"name": name, "params": json.dumps(params), "nf": len(frames),
             "cap": captured, "meta": json.dumps({"spec": spec})})).scalar_one()

    # The manifest travels in the message (it is selection output, not a secret), but the
    # callback URL and token do NOT: the worker reads those from its own environment, so a
    # compromised broker can neither redirect the artifacts nor learn the token.
    actors.reconstruct_cluster.send({
        "result_id": str(rid), "name": name, "center": [req.lat, req.lon],
        "params": params, "frames": frames,
    })
    print(f"recon: enqueued {rid} '{name}' with {len(frames)} frames", flush=True)
    return {"queued": str(rid), "name": name, "n_frames": len(frames)}


@router.post("/recon/preview")
async def preview_selection(req: EnqueueRequest):
    """What would be selected, without enqueueing — the cluster is the decision that
    matters most (never subsample a sweep), so it should be inspectable first."""
    frames = await _select_frames(req)
    # Sharing one focal is physically correct exactly when the frames come from one camera
    # at one zoom. Identity from EXIF where it survived, owner+dimensions otherwise; and a
    # single EXIF focal across the cluster is the strongest form of the condition, because
    # then the shared value is not merely shared but *known*.
    # Whether ONE focal may be solved for the cluster is not just "same camera". What
    # produced the pixels is the camera *and the pics pipeline*, whose lens-geometry
    # correction has changed over time — so a change in frame dimensions signals a change
    # in effective intrinsics even from the identical body, and exact equality is the right
    # test rather than a tolerance. Capture date is the processing-stability window: a
    # series shot in one day can be trusted to have had the same processing applied.
    cams = {f.get("camera") for f in frames}
    dims = {(f["width"], f["height"]) for f in frames}
    days = {(f.get("captured_at") or "")[:10] for f in frames if f.get("captured_at")}
    focals = {f.get("exif_focal_px_512") for f in frames if f.get("exif_focal_px_512")}
    # Time proximity corroborates device identity: frames minutes apart from one device are
    # one session with one lens setting, whereas the same device months apart may have had
    # its zoom changed. Reported so the caller can weigh it; not folded into the boolean,
    # because a legitimate cross-date fuse of one camera is still one camera.
    caps = sorted(f["captured_at"] for f in frames if f.get("captured_at"))
    span_s = None
    if len(caps) >= 2:
        try:
            span_s = round((datetime.datetime.fromisoformat(caps[-1])
                            - datetime.datetime.fromisoformat(caps[0])).total_seconds())
        except ValueError:
            span_s = None
    return {"n_frames": len(frames),
            # the three axes, reported separately so a warning can say WHICH one failed
            "single_camera": len(cams) == 1,
            "same_dimensions": len(dims) == 1,
            "same_day": len(days) <= 1,
            "uniform_capture": len(cams) == 1 and len(dims) == 1 and len(days) <= 1,
            "cameras": sorted(c for c in cams if c),
            "days": sorted(days),
            "camera_id_source": (sorted(cams)[0].split(":", 1)[0]
                                 if len(cams) == 1 and any(cams) else "mixed"),
            "capture_span_s": span_s,
            "same_session": bool(span_s is not None and span_s <= 3600
                                 and len(cams) == 1),
            "dimensions": sorted(f"{w}x{h}" for w, h in dims),
            # "known" means every frame reports one, and they agree to within 2% — a zoom
            # ring nudged between shots is still one focal for our purposes (0.75% spread
            # on the 16-35 mm set is worth under 2 px)
            "exif_focal_px_512": (round(sum(focals) / len(focals)) if focals else None),
            "exif_focal_spread": (round((max(focals) - min(focals)) / max(focals), 4)
                                  if focals else None),
            "exif_focal_known": bool(
                focals and all(f.get("exif_focal_px_512") for f in frames)
                and (max(focals) - min(focals)) / max(focals) <= 0.02),
            "frames": [{k: f[k] for k in ("id", "lat", "lon", "captured_at",
                                          "compass_angle", "title")} for f in frames]}


def _write_atomic(path: str, data: bytes) -> None:
    """Temp + replace, so a client mid-download never sees a half-written artifact."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


RESULT_FILES = {
    "metadata": ("metadata.json", "metadata_path"),
    "metrics": ("metrics.json", "metrics_path"),
    "cloud": ("points.ply", "cloud_path"),
    "topdown": ("topdown.png", "topdown_path"),
    "pairs_matrix": ("pairs_matrix.png", "pairs_matrix_path"),
    "log": ("run.log", "log_path"),
}


@router.post("/recon/result")
async def result(result_json: str = Form(...),
                 metadata: UploadFile | None = File(None),
                 metrics: UploadFile | None = File(None),
                 cloud: UploadFile | None = File(None),
                 topdown: UploadFile | None = File(None),
                 pairs_matrix: UploadFile | None = File(None),
                 log: UploadFile | None = File(None),
                 x_worker_token: str = Header(None)):
    """Worker callback. Accepts progress posts (status='running') and the final result.

    Only the sparse layer comes back — the run dir and its 1.8-2.7 GB forward-pass cache
    stay on the worker, regenerable and only needed to re-solve.
    """
    if x_worker_token != WORKER_TOKEN:
        raise HTTPException(403, "bad worker token")
    d = json.loads(result_json)
    try:
        # canonical uuid BEFORE any filesystem use: result_id names the artifact
        # directory, so a traversal payload must be rejected before bytes land
        rid = str(uuid.UUID(str(d["result_id"])))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "result_id must be a uuid")

    uploads = {"metadata": metadata, "metrics": metrics, "cloud": cloud,
               "topdown": topdown, "pairs_matrix": pairs_matrix, "log": log}
    cols: dict[str, str] = {}
    for key, up in uploads.items():
        if up is None:
            continue
        fname, col = RESULT_FILES[key]
        rel = os.path.join("recon", rid, fname)
        _write_atomic(_artifact_abspath(rel), await up.read())
        cols[col] = rel

    summary = _summary(d.get("metrics") or {}) or None
    running = d.get("status") == "running"
    sets = ["status = :st", "worker = COALESCE(:w, worker)"]
    args: dict = {"st": "running" if running else d.get("status", "done"),
                  "w": d.get("worker"), "id": rid}
    # meta is MERGED so a progress ping can't wipe the spec recorded at enqueue
    if d.get("meta"):
        sets.append("meta = COALESCE(meta, '{}'::jsonb) || CAST(:meta AS jsonb)")
        args["meta"] = json.dumps(d["meta"])
    if summary:
        sets.append("metrics = CAST(:metrics AS jsonb)")
        args["metrics"] = json.dumps(summary)
    for k in ("n_frames", "n_pairs"):
        if d.get(k) is not None:
            sets.append(f"{k} = :{k}")
            args[k] = d[k]
    for col, rel in cols.items():
        sets.append(f"{col} = :{col}")
        args[col] = rel
    if running:
        # a late out-of-order ping must not resurrect a finished run
        where = " AND status NOT IN ('done', 'error')"
    else:
        sets.append("error = :err")
        sets.append("finished_at = now()")
        args["err"] = d.get("error")
        where = ""
    async with wb_engine.begin() as conn:
        await conn.execute(text(
            f"UPDATE recon_runs SET {', '.join(sets)} "
            f"WHERE id = CAST(:id AS uuid){where}"), args)
    return {"ok": True}


# "Queued with zero consumers" is silent otherwise — the recon worker is a host process
# the stack cannot see — so the runs list carries the queue's counts and the bench can say
# "no worker connected" instead of looking merely slow.
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
                q = ch.queue.declare("recon", passive=True)
                return {"messages": q["message_count"],
                        "consumers": q["consumer_count"]}
    except amqpstorm.AMQPError:
        return None  # unreachable broker / missing queue → unknown, not an error


async def _queue_state() -> dict | None:
    global _queue_state_cache
    now = time.monotonic()
    if _queue_state_cache and now - _queue_state_cache[0] < QUEUE_STATE_TTL_S:
        return _queue_state_cache[1]
    import asyncio
    state = await asyncio.to_thread(_queue_state_now)
    _queue_state_cache = (now, state)
    return state


class ImportRequest(BaseModel):
    names: list[str] | None = None   # default: every run dir that has metrics.json
    archive_dir: str | None = None   # override for tests


@router.post("/recon/import")
async def import_archived(req: ImportRequest):
    """Ingest archived run dirs from scripts/enrich/runs into the bench.

    This is how the bench has content before the queue exists. Idempotent: re-importing
    a run updates its row and re-copies the artifacts (metrics get recomputed as the
    metric improves, so refresh must be cheap and safe). A run dir without metrics.json
    is skipped rather than half-imported — run recon_metrics.py over it first.
    """
    root = os.path.realpath(req.archive_dir or ARCHIVE_ROOT)
    if not os.path.isdir(root):
        raise HTTPException(400, f"archive dir not found: {root}")
    names = req.names or sorted(
        d for d in os.listdir(root)
        if os.path.exists(os.path.join(root, d, "metrics.json")))

    imported, skipped = [], []
    for name in names:
        src = os.path.join(root, name)
        mpath = os.path.join(src, "metrics.json")
        if not os.path.exists(mpath):
            skipped.append({"name": name, "reason": "no metrics.json"})
            continue
        with open(mpath) as f:
            metrics = json.load(f)
        meta = {}
        mdpath = os.path.join(src, "metadata.json")
        if os.path.exists(mdpath):
            with open(mdpath) as f:
                md = json.load(f)
            meta = {"stats": md.get("stats"), "alignment": md.get("alignment"),
                    "center": md.get("center")}
            params = md.get("args") or {}
            # asyncpg binds before the CAST, so hand it a real date, not a string
            iso = ((md.get("frames") or [{}])[0].get("captured_at") or "")[:10]
            try:
                captured = datetime.date.fromisoformat(iso) if iso else None
            except ValueError:
                captured = None
        else:
            params, captured = {}, None

        async with wb_engine.begin() as conn:
            rid = (await conn.execute(text(
                "INSERT INTO recon_runs (name, source, params, status, n_frames, "
                "  n_pairs, captured_on, metrics, meta, finished_at) "
                "VALUES (:name, 'imported', CAST(:params AS jsonb), 'done', :nf, :np, "
                "  CAST(:cap AS date), CAST(:metrics AS jsonb), CAST(:meta AS jsonb), now()) "
                "ON CONFLICT (name, source) DO UPDATE SET "
                "  params = EXCLUDED.params, n_frames = EXCLUDED.n_frames, "
                "  n_pairs = EXCLUDED.n_pairs, captured_on = EXCLUDED.captured_on, "
                "  metrics = EXCLUDED.metrics, meta = EXCLUDED.meta, "
                "  status = 'done', error = NULL, finished_at = now() "
                "RETURNING id"),
                {"name": name, "params": json.dumps(params),
                 "nf": metrics.get("n_frames"), "np": metrics.get("n_pairs"),
                 "cap": captured, "metrics": json.dumps(_summary(metrics)),
                 "meta": json.dumps(meta)})).scalar()

            dest_rel = os.path.join("recon", str(rid))
            dest = _artifact_abspath(dest_rel)
            os.makedirs(dest, exist_ok=True)
            cols = {}
            for col, fname in ARTIFACT_FILES.items():
                s = os.path.join(src, fname)
                if not os.path.exists(s):
                    continue
                shutil.copy2(s, os.path.join(dest, fname))
                cols[col] = os.path.join(dest_rel, fname)
            # run log sits beside the dir, not inside it
            log_src = os.path.join(root, f"{name}.log")
            if os.path.exists(log_src):
                shutil.copy2(log_src, os.path.join(dest, "run.log"))
                cols["log_path"] = os.path.join(dest_rel, "run.log")
            if cols:
                sets = ", ".join(f"{c} = :{c}" for c in cols)
                await conn.execute(text(
                    f"UPDATE recon_runs SET {sets} WHERE id = CAST(:id AS uuid)"),
                    cols | {"id": str(rid)})
        imported.append({"name": name, "id": str(rid), "artifacts": sorted(cols)})
    return {"imported": imported, "skipped": skipped, "archive_dir": root}
