"""Matching bench API: view-pie candidates (live knobs), verdict facts, and
MASt3R pair jobs via the queue (results POSTed back by the worker)."""
import datetime
import json
import os
import uuid as uuid_mod

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text

from .. import config, facts, graph, matching
from ..db import wb_engine
from ..runs import create_run, finish_run
from .calibrate import _calibration_rows

router = APIRouter()

WORKER_TOKEN = os.getenv("ENRICH_WORKER_TOKEN", "dev-worker-token")
CALLBACK_BASE = os.getenv("WORKER_CALLBACK_BASE", "http://127.0.0.1:8070")


async def _target_for(ann_id: str) -> dict:
    """The annotation's target point = its picked anchor (approved > wiki > auto),
    same choice the calibration bench makes."""
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT a.photo_id FROM annotation_mirror a WHERE a.id = :id"),
            {"id": ann_id})).first()
    if not row:
        raise HTTPException(404, "annotation not found")
    data = await _calibration_rows(row.photo_id)
    for r in data["rows"]:
        if r["annotation_id"] == ann_id:
            if not r["anchor"]:
                raise HTTPException(422, f"no usable anchor for annotation ({r['rule']})")
            return {"pano": data["photo"], "row": r,
                    "lat": r["anchor"]["lat"], "lon": r["anchor"]["lon"]}
    raise HTTPException(404, "annotation not in its photo's rows")


async def _photo_pool(exclude_id: str, lon: float, lat: float, radius_m: float):
    async with wb_engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT id, ST_X(geometry) AS lon, ST_Y(geometry) AS lat, compass_angle, "
            "(analysis->>'farthest_object_distance')::float AS far_m, title, "
            "width, height "
            "FROM photo_mirror WHERE deleted = false AND missing_since IS NULL "
            "AND geometry IS NOT NULL AND compass_angle IS NOT NULL AND id != :pid "
            "AND ST_DWithin(geometry::geography, "
            "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :rad)"),
            {"pid": exclude_id, "lon": lon, "lat": lat, "rad": radius_m})).all()


async def _photo_pool_bbox(exclude_id: str, minlon: float, minlat: float,
                           maxlon: float, maxlat: float, limit: int):
    """Photos whose position falls in the given lon/lat box (the map viewport) —
    the manual-scan pool, no pie/distance gate."""
    async with wb_engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT id, ST_X(geometry) AS lon, ST_Y(geometry) AS lat, compass_angle, "
            "(analysis->>'farthest_object_distance')::float AS far_m, title, "
            "width, height "
            "FROM photo_mirror WHERE deleted = false AND missing_since IS NULL "
            "AND geometry IS NOT NULL AND compass_angle IS NOT NULL AND id != :pid "
            "AND geometry && ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326) "
            "LIMIT :lim"),
            {"pid": exclude_id, "minlon": minlon, "minlat": minlat,
             "maxlon": maxlon, "maxlat": maxlat, "lim": limit})).all()


async def _pano_pie(photo_id: str, compass, slack: float, default_far: float,
                    assumed_fov: float) -> dict | None:
    """The ORIGIN pano's own view pie: calibrated centre/FOV when available
    (compass ± assumed_fov/2 otherwise), radius from its LLM far distance."""
    from .proto import _calibration_for
    cal = await _calibration_for(photo_id)
    async with wb_engine.connect() as conn:
        far = (await conn.execute(text(
            "SELECT (analysis->>'farthest_object_distance')::float "
            "FROM photo_mirror WHERE id = :id"), {"id": photo_id})).scalar()
    bearing = cal["centre_bearing"] if cal else compass
    if bearing is None:
        return None
    return {"bearing": round(bearing, 1),
            "half": round((cal["fov"] if cal else assumed_fov) / 2, 1),
            "radius_m": round((far or default_far) * slack),
            "calibrated": cal is not None}


async def _annotation_pie(ann_id: str, slack: float, default_far: float,
                          assumed_fov: float) -> dict | None:
    """The single annotation's EXACT angular slice: its rect's left..right edges
    mapped through the pano calibration (no uncertainty padding — the wedge is
    the search region, this is the measurement)."""
    from .proto import _calibration_for
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT a.target, a.photo_id, p.compass_angle, "
            "(p.analysis->>'farthest_object_distance')::float AS far_m "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = :id"), {"id": ann_id})).first()
    if not row or row.compass_angle is None:
        return None
    try:
        g = (row.target.get("selector") or {}).get("geometry") or {}
        x, w = float(g["x"]), float(g.get("w", 0.005))
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    cal = await _calibration_for(row.photo_id)
    centre = cal["centre_bearing"] if cal else row.compass_angle
    fov = cal["fov"] if cal else assumed_fov
    return {"bearing": round((centre + (x + w / 2 - 0.5) * fov) % 360, 2),
            "half": round(max(0.3, w * fov / 2), 2),
            "radius_m": round((row.far_m or default_far) * slack),
            "calibrated": cal is not None}


def _cand_dict(r, slack: float, half: float, default_far: float) -> dict:
    """Common candidate payload incl. its own view pie (for map hover-drawing)."""
    return {"photo_id": r.id, "lat": r.lat, "lon": r.lon,
            "bearing": r.compass_angle, "far_m": r.far_m,
            "title": r.title, "width": r.width, "height": r.height,
            "pie": {"bearing": r.compass_angle, "half": half,
                    "radius_m": round((r.far_m or default_far) * slack)}}


@router.get("/annotations/{ann_id}/view_candidates")
async def view_candidates(ann_id: str, slack: float = 2.0, half: float = 60,
                          sameside: float = 90, default_far: float = 2000,
                          limit: int = 60, mode: str = "auto",
                          ray_half: float | None = None, near_m: float = 200,
                          far_m: float = 15000, assumed_fov: float = 90,
                          overlap: bool = True, bbox: str | None = None):
    """Candidates for matching, three modes:
    - target (anchor known): photos whose view pie contains the anchor point +
      same-side constraint — the confirmation flow.
    - ray (no anchor — e.g. a bare '?' rect): the pano's calibration turns the
      rect-x into an azimuth; the unknown sits somewhere on that ray. Wedge =
      azimuth ± ray_half over [near_m, far_m]. overlap=true additionally demands
      the candidate's own pie SEE the ray (tested by sampling points along it —
      viewpie×viewpie via the existing point gate); overlap=false is plain
      position-in-wedge. mode=auto picks target when an anchor exists.
    - bbox (mode=bbox, bbox=minlon,minlat,maxlon,maxlat): every photo in the map
      viewport, no geometric gate — manual visual scanning by pan+zoom."""
    target = wedge = None
    pano = None
    if mode == "bbox":
        if not bbox:
            raise HTTPException(422, "bbox mode needs bbox=minlon,minlat,maxlon,maxlat")
        try:
            minlon, minlat, maxlon, maxlat = (float(x) for x in bbox.split(","))
        except (ValueError, TypeError):
            raise HTTPException(422, "bbox must be minlon,minlat,maxlon,maxlat")
        async with wb_engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT a.photo_id, ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat, "
                "p.compass_angle FROM annotation_mirror a "
                "JOIN photo_mirror p ON p.id = a.photo_id WHERE a.id = :id"),
                {"id": ann_id})).first()
        if not row:
            raise HTTPException(404, "annotation not found")
        pano = {"id": row.photo_id, "lat": row.lat, "lon": row.lon,
                "compass_angle": row.compass_angle}
        from ..calibrate import haversine_km
        rows = await _photo_pool_bbox(row.photo_id, minlon, minlat, maxlon, maxlat, limit)
        cands = []
        for r in rows:
            c = _cand_dict(r, slack, half, default_far)
            c["dist_m"] = (round(haversine_km(row.lon, row.lat, r.lon, r.lat) * 1000)
                           if row.lat is not None and r.lat is not None else 0)
            c["off"] = 0
            cands.append(c)
        used_mode = "bbox"
    elif mode in ("auto", "target"):
        try:
            t = await _target_for(ann_id)
            pano = t["pano"]
            target = t
        except HTTPException as e:
            if mode == "target" or e.status_code == 404:
                raise

    if mode == "bbox":
        pass  # candidates already built above
    elif target:
        rows = await _photo_pool(pano["id"], t["lon"], t["lat"], 25000)
        cands = []
        for r in rows:
            hit = matching.in_pie(
                {"lat": r.lat, "lon": r.lon, "bearing": r.compass_angle, "far_m": r.far_m},
                t["lat"], t["lon"], slack=slack, half=half, default_far=default_far)
            if not hit:
                continue
            if pano["lat"] is not None and not matching.same_side(
                    pano["lat"], pano["lon"], r.lat, r.lon, t["lat"], t["lon"], sameside):
                continue
            cands.append({**_cand_dict(r, slack, half, default_far), **hit})
        used_mode = "target"
    else:
        # ray mode: pano position + calibration (or compass + assumed FOV) +
        # rect-x → sight ray with angular uncertainty
        from ..calibrate import ang_norm, bearing_deg, haversine_km, rect_x
        from .proto import _calibration_for
        async with wb_engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT a.target, a.photo_id, ST_X(p.geometry) AS lon, "
                "ST_Y(p.geometry) AS lat, p.compass_angle "
                "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
                "WHERE a.id = :id"), {"id": ann_id})).first()
        if not row:
            raise HTTPException(404, "annotation not found")
        if row.lat is None or row.compass_angle is None:
            raise HTTPException(422, "ray mode needs the pano's position and compass")
        rx = rect_x(row.target)
        if rx is None:
            raise HTTPException(422, "ray mode needs an annotation rect")
        cal = await _calibration_for(row.photo_id)
        if cal:
            fov, rms = cal["fov"], cal.get("rms") or 5.0
            azimuth = (cal["centre_bearing"] + (rx - 0.5) * fov) % 360
        else:
            fov, rms = assumed_fov, 15.0
            azimuth = (row.compass_angle + (rx - 0.5) * fov) % 360
        try:
            g = (row.target.get("selector") or {}).get("geometry") or {}
            rect_w_deg = float(g.get("w", 0.01)) * fov
        except (AttributeError, TypeError, ValueError):
            rect_w_deg = 0.01 * fov
        if ray_half is None:
            ray_half = min(45.0, max(3.0, rect_w_deg / 2 + rms))
        wedge = {"lat": row.lat, "lon": row.lon, "azimuth": round(azimuth, 2),
                 "half": round(ray_half, 1), "near_m": near_m, "far_m": far_m,
                 "calibrated": cal is not None, "rect_x": round(rx, 4)}
        pano = {"id": row.photo_id, "lat": row.lat, "lon": row.lon,
                "compass_angle": row.compass_angle}

        rows = await _photo_pool(row.photo_id, row.lon, row.lat, far_m + 5000)
        # ray sample points for the pie-overlap test
        step = max(200.0, (far_m - near_m) / 32)
        samples = []
        m = near_m
        while m <= far_m:
            slat, slon = matching.dest_point(row.lat, row.lon, azimuth, m)
            samples.append((m, slat, slon))
            m += step
        cands = []
        for r in rows:
            d_m = haversine_km(row.lon, row.lat, r.lon, r.lat) * 1000
            off_ray = ang_norm(bearing_deg(row.lon, row.lat, r.lon, r.lat) - azimuth)
            in_wedge = near_m <= d_m <= far_m and abs(off_ray) <= ray_half
            # proximity to the ray = proximity to the unknown → the ranking that
            # matters (dist to pano is meaningless here: the pano's neighbors
            # trivially see the near end of a long ray)
            ray_dist = min(haversine_km(r.lon, r.lat, slon, slat) * 1000
                           for _, slat, slon in samples)
            hit_range = None
            if overlap:
                photo = {"lat": r.lat, "lon": r.lon, "bearing": r.compass_angle,
                         "far_m": r.far_m}
                hits = [m for m, slat, slon in samples
                        if matching.in_pie(photo, slat, slon, slack=slack,
                                           half=half, default_far=default_far)]
                if hits:
                    hit_range = [round(min(hits)), round(max(hits))]
            qualifies = bool(hit_range) if overlap else in_wedge
            if not qualifies:
                continue
            cands.append({**_cand_dict(r, slack, half, default_far),
                          "dist_m": round(d_m), "off": round(off_ray, 1),
                          "ray_dist_m": round(ray_dist),
                          "in_wedge": in_wedge, "hit_range": hit_range})
        used_mode = "ray"

    cands.sort(key=lambda c: c.get("ray_dist_m", c["dist_m"]))
    total = len(cands)
    cands = cands[:limit]

    # attach sizes (page only), latest match result, and verdict fact status
    ids = [c["photo_id"] for c in cands]
    if ids:
        async with wb_engine.connect() as conn:
            sizes = {r.id: r.sizes for r in (await conn.execute(text(
                "SELECT id, sizes FROM photo_mirror WHERE id = ANY(:ids)"),
                {"ids": ids})).all()}
            mres = {}
            for r in (await conn.execute(text(
                "SELECT DISTINCT ON (photo_id) photo_id, id, status, raw_matches, "
                "inliers, ratio, overlay_path FROM match_results "
                "WHERE annotation_id = :aid AND photo_id = ANY(:ids) "
                "ORDER BY photo_id, enqueued_at DESC"),
                {"aid": ann_id, "ids": ids})).all():
                mres[r.photo_id] = dict(r._mapping)
        verdicts = await _verdicts_for(ann_id, ids)
        for c in cands:
            c["sizes"] = sizes.get(c["photo_id"])
            c["match"] = mres.get(c["photo_id"])
            c["verdict"] = verdicts.get(c["photo_id"], "none")

    return {"mode": used_mode,
            "target": ({"lat": target["lat"], "lon": target["lon"],
                        "anchor": target["row"]["anchor"]["candidate"],
                        "rule": target["row"]["rule"]} if target else None),
            "wedge": wedge,
            "annotation_pie": await _annotation_pie(ann_id, slack, default_far,
                                                    assumed_fov),
            "pano": {"id": pano["id"], "lat": pano["lat"], "lon": pano["lon"],
                     "bearing": pano["compass_angle"],
                     "pie": await _pano_pie(pano["id"], pano["compass_angle"],
                                            slack, default_far, assumed_fov)},
            "total": total, "candidates": cands}


async def _verdicts_for(ann_id: str, photo_ids: list[str]) -> dict[str, str]:
    ann = graph.annotation_iri(ann_id)
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?ph ?status WHERE {{
  GRAPH ?f {{ <{ann}> hv:depictedIn ?ph }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    out = {}
    for b in res["results"]["bindings"]:
        pid = b["ph"]["value"].rsplit("/", 1)[-1]
        out[pid] = (b["status"]["value"].split("#")[-1]
                    if "status" in b else "proposed")
    return out


class VerdictRequest(BaseModel):
    annotation_id: str
    photo_id: str
    verdict: str            # true | false | unset


@router.post("/matching/verdict")
async def verdict(req: VerdictRequest):
    if req.verdict not in ("true", "false", "unset"):
        raise HTTPException(422, "verdict must be true | false | unset")
    ann = facts.iri(graph.annotation_iri(req.annotation_id))
    ph = facts.iri(graph.photo_iri(req.photo_id))
    s, p, o = ann, facts._p("depictedIn"), ph
    h = facts.fact_hash(s, p, o)
    g = graph.fact_iri(h)

    run_id = await create_run(kind="verdict", params=req.model_dump())
    await graph.store.load_turtle(g, f"{s} {p} {o} .\n")
    run = facts.iri(graph.run_iri(run_id))
    await graph.store.load_turtle(
        graph.GRAPH_META,
        f"{facts.iri(g)} <http://www.w3.org/ns/prov#wasGeneratedBy> {run} .\n"
        f"{facts.iri(g)} {facts._p('about')} {ann} .\n")
    decision = {"true": "approved", "false": "rejected", "unset": "proposed"}[req.verdict]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    await graph.store.update(facts.curate_update(g, decision, decided_at_iso=now))
    await finish_run(run_id, stats={"fact": g, "decision": decision})
    return {"fact": g, "decision": decision}


class EnqueueRequest(BaseModel):
    annotation_id: str
    photo_ids: list[str]
    matcher: str = "mast3r"


@router.post("/matching/enqueue")
async def enqueue(req: EnqueueRequest):
    from .. import actors
    if not actors.init_broker():
        raise HTTPException(503, "no RABBITMQ_URL configured")

    async with wb_engine.connect() as conn:
        ann = (await conn.execute(text(
            "SELECT a.id, a.target, a.photo_id, p.sizes, p.width, p.height "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = :id"), {"id": req.annotation_id})).first()
        if not ann:
            raise HTTPException(404, "annotation not found")
        photos = {r.id: r.sizes for r in (await conn.execute(text(
            "SELECT id, sizes FROM photo_mirror WHERE id = ANY(:ids)"),
            {"ids": req.photo_ids})).all()}

    g = (ann.target.get("selector") or {}).get("geometry") or {}
    rect = [float(g.get("x", 0)), float(g.get("y", 0)),
            float(g.get("w", 0)), float(g.get("h", 0))]
    full = (ann.sizes or {}).get("full") or {}
    queued = []
    for pid in req.photo_ids:
        psizes = photos.get(pid) or {}
        purl = ((psizes.get("full") or {}).get("url"))
        if not purl:
            continue
        rid = str(uuid_mod.uuid4())
        async with wb_engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO match_results (id, annotation_id, photo_id, matcher, params) "
                "VALUES (CAST(:id AS uuid), :aid, :pid, :m, CAST(:p AS jsonb))"),
                {"id": rid, "aid": req.annotation_id, "pid": pid, "m": req.matcher,
                 "p": json.dumps({"rect": rect})})
        actors.match_pair.send({
            "result_id": rid,
            "matcher": req.matcher,
            "crop": {"rect": rect, "full_url": full.get("url"),
                     "pyramid": full.get("pyramid"),
                     "width": ann.width, "height": ann.height},
            "photo_url": purl,
            "callback": f"{CALLBACK_BASE}/api/matching/result",
            "token": WORKER_TOKEN,
        })
        queued.append(rid)
    return {"queued": queued}


@router.post("/matching/result")
async def result(result_json: str = Form(...),
                 overlay: UploadFile | None = File(None),
                 x_worker_token: str = Header(None)):
    if x_worker_token != WORKER_TOKEN:
        raise HTTPException(403, "bad worker token")
    d = json.loads(result_json)
    overlay_path = None
    if overlay is not None:
        os.makedirs(os.path.join(config.ARTIFACTS_DIR, "matching"), exist_ok=True)
        overlay_path = os.path.join("matching", f"{d['result_id']}.jpg")
        with open(os.path.join(config.ARTIFACTS_DIR, overlay_path), "wb") as f:
            f.write(await overlay.read())
    async with wb_engine.begin() as conn:
        await conn.execute(text(
            "UPDATE match_results SET status = :st, raw_matches = :raw, "
            "inliers = :inl, ratio = :ratio, error = :err, overlay_path = :ov, "
            "worker = :w, finished_at = now() WHERE id = CAST(:id AS uuid)"),
            {"st": d.get("status", "done"), "raw": d.get("raw"),
             "inl": d.get("inliers"), "ratio": d.get("ratio"),
             "err": d.get("error"), "ov": overlay_path,
             "w": d.get("worker"), "id": d["result_id"]})
    return {"ok": True}


@router.get("/matching/results")
async def results(annotation_id: str):
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT * FROM match_results WHERE annotation_id = :aid "
            "ORDER BY enqueued_at DESC LIMIT 200"), {"aid": annotation_id})).all()
    return [dict(r._mapping) for r in rows]


@router.get("/matching/overlay/{result_id}")
async def overlay(result_id: str):
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT overlay_path FROM match_results WHERE id = CAST(:id AS uuid)"),
            {"id": result_id})).first()
    if not row or not row.overlay_path:
        raise HTTPException(404, "no overlay")
    return FileResponse(os.path.join(config.ARTIFACTS_DIR, row.overlay_path),
                        media_type="image/jpeg")
