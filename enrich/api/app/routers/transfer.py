"""Pano→pano annotation transfer bench.

Clones annotations from donor panos onto a target pano of the same spot.
Per annotation: COARSE pass (azimuth-prior window + ~15° scale-matched donor
context → MASt3R → projected rect) then a tight REFINE pass around the coarse
fix (~10× the rect; the 15°-slice homography carries ~0.1° model error from
pano-projection differences + parallax). Accepted transfers become
workbench-native annotations on the target (→ existing create_annotation
graduation), linked by an approved hv:derivedFrom fact and a shared POI
(donor's POI reused, minted otherwise — acceptance is the identity assertion).

The azimuth prior is SELF-IMPROVING: every confident projection is a
(azimuth ↦ target-x, local px/°) datapoint; prediction uses the nearest
datapoint — naturally piecewise, so stitching bends are absorbed as coverage
grows. With no datapoints yet, a SWEEP seeds the first one by scanning the
whole target width with one (big, distinctive) annotation.

Pipeline state is derived from match_results rows carrying params.transfer_id
(stage: sweep|coarse|refine); the transfers table records only decisions.
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import facts, graph
from ..db import wb_engine
from ..parser import parse_body
from ..runs import create_run, fail_run, finish_run
from .annotations import NativeAnnotationCreate, create_native_annotation
from .matching import enqueue_pair
from .poi import CreatePoiRequest, RelateRequest, _mint_approved, create_poi, relate_annotation
from .proto import _calibration_for

router = APIRouter()

CONF_INLIERS = 100      # h_inliers ≥ this ⇒ projection usable as a datapoint
COARSE_DEG = 15.0       # angular span of the coarse context (and ideally window)
ASSUMED_FOV = 90.0      # uncalibrated donor fallback
SWEEP_W, SWEEP_STEP = 0.13, 0.065


def _rect_of(target) -> dict | None:
    try:
        g = (target.get("selector") or {}).get("geometry") or {}
        return {k: float(g[k]) for k in ("x", "y", "w", "h")}
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _angdiff(a: float, b: float) -> float:
    """Signed shortest a−b in degrees, in [-180, 180)."""
    return (a - b + 180.0) % 360.0 - 180.0


async def _donor_cal(photo_id: str, compass) -> dict | None:
    """{centre, fov, calibrated} for a donor pano; compass±ASSUMED_FOV fallback."""
    cal = await _calibration_for(photo_id)
    if cal:
        return {"centre": cal["centre_bearing"], "fov": cal["fov"], "calibrated": True}
    if compass is not None:
        return {"centre": float(compass), "fov": ASSUMED_FOV, "calibrated": False}
    return None


def _azimuth(rect: dict, cal: dict) -> float:
    return (cal["centre"] + (rect["x"] + rect["w"] / 2 - 0.5) * cal["fov"]) % 360


# ---------------------------------------------------------------------------
# results / datapoints / prediction
# ---------------------------------------------------------------------------

async def _transfer_results(transfer_ids: list[str]) -> dict[str, list[dict]]:
    """All match rows belonging to these transfers, keyed by transfer id."""
    if not transfer_ids:
        return {}
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, params, status, raw_matches, inliers, projection, error, "
            "overlay_path IS NOT NULL AS has_overlay, enqueued_at "
            "FROM match_results WHERE params->>'transfer_id' = ANY(:ids) "
            "ORDER BY enqueued_at"), {"ids": transfer_ids})).all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        proj = r.projection or {}
        out.setdefault(r.params["transfer_id"], []).append({
            "result_id": str(r.id), "stage": r.params.get("stage", "coarse"),
            "window": r.params.get("window"), "status": r.status,
            "raw": r.raw_matches, "inliers": r.inliers,
            "h_inliers": int(proj.get("h_inliers") or 0),
            "bbox": proj.get("bbox"), "method": proj.get("method"),
            "has_overlay": r.has_overlay, "error": r.error})
    return out


def _best(results: list[dict], stages: tuple[str, ...]) -> dict | None:
    done = [r for r in results if r["stage"] in stages
            and r["status"] == "done" and r.get("bbox")]
    return max(done, key=lambda r: r["h_inliers"], default=None)


def _proposed(results: list[dict]) -> tuple[dict | None, str | None]:
    """Best available bbox: confident refine beats coarse/sweep."""
    ref = _best(results, ("refine",))
    if ref and ref["h_inliers"] >= CONF_INLIERS:
        return ref["bbox"], "refine"
    coarse = _best(results, ("coarse", "sweep"))
    if coarse and coarse["h_inliers"] >= CONF_INLIERS:
        return coarse["bbox"], coarse["stage"]
    return None, None


async def _datapoints(target_photo_id: str, target_w: int) -> list[dict]:
    """(azimuth ↦ target x-center, local px/°) from every confident projection
    of a calibrated-donor annotation onto this target — the warp observations."""
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT m.projection, a.target, a.photo_id, p.compass_angle "
            "FROM match_results m "
            "JOIN annotation_mirror a ON a.id = m.annotation_id "
            "JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE m.photo_id = :tid AND m.status = 'done' "
            "AND m.params ? 'transfer_id' AND m.projection IS NOT NULL"),
            {"tid": target_photo_id})).all()
    cals: dict[str, dict | None] = {}
    dps = []
    for r in rows:
        proj = r.projection or {}
        bbox = proj.get("bbox")
        if not bbox or int(proj.get("h_inliers") or 0) < CONF_INLIERS:
            continue
        rect = _rect_of(r.target)
        if not rect:
            continue
        if r.photo_id not in cals:
            cals[r.photo_id] = await _donor_cal(r.photo_id, r.compass_angle)
        cal = cals[r.photo_id]
        # only CALIBRATED donors contribute datapoints — compass-only azimuths
        # (±10°+) would corrupt the az↦x curve for everyone else
        if not cal or not cal["calibrated"]:
            continue
        dp = {"az": _azimuth(rect, cal), "x": bbox["x"] + bbox["w"] / 2,
              "h_inliers": int(proj["h_inliers"]), "calibrated": cal["calibrated"]}
        deg = rect["w"] * cal["fov"]
        if deg > 0.02 and bbox["w"] > 0:   # hairline rects give no usable scale
            dp["pxdeg"] = bbox["w"] * target_w / deg
        dps.append(dp)
    return dps


def _predict(az: float, dps: list[dict], target_w: int) -> dict | None:
    """Nearest-datapoint linear prediction of the target x-center for an
    azimuth, with distance-growing slack (the bend shows up as extrapolation
    error, so slack widens away from observed anchors)."""
    if not dps:
        return None
    scales = [d["pxdeg"] for d in dps if d.get("pxdeg")]
    if not scales:
        return None
    scales.sort()
    pxdeg = scales[len(scales) // 2]
    dp = min(dps, key=lambda d: abs(_angdiff(az, d["az"])))
    ddeg = _angdiff(az, dp["az"])
    x = dp["x"] + ddeg * (dp.get("pxdeg") or pxdeg) / target_w
    slack_deg = 2.0 + 0.15 * abs(ddeg)
    return {"x": x, "slack_deg": slack_deg, "pxdeg": dp.get("pxdeg") or pxdeg,
            "anchor_az": dp["az"], "dist_deg": abs(ddeg)}


def _coarse_specs(rect: dict, cal: dict, pred: dict, target_w: int):
    """→ (window, context) [x,y,w,h] for the coarse pass: ~15° donor slice vs a
    prior window of ≈ the same angular span (scale match)."""
    pxdeg = pred["pxdeg"]
    rect_deg = rect["w"] * cal["fov"]
    span = max(COARSE_DEG * pxdeg / target_w,
               (rect_deg + 2 * pred["slack_deg"]) * pxdeg / target_w)
    x0 = min(max(pred["x"] - span / 2, 0.0), 1.0 - span)
    window = [round(x0, 5), 0.0, round(span, 5), 1.0]
    ctx_w = min(COARSE_DEG / cal["fov"], 1.0)
    cx0 = min(max(rect["x"] + rect["w"] / 2 - ctx_w / 2, 0.0), 1.0 - ctx_w)
    context = [round(cx0, 5), 0.0, round(ctx_w, 5), 1.0]
    return window, context


def _refine_specs(rect: dict, bbox: dict):
    """Tight matched-scale second pass around the coarse fix (~10× the rect)."""
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))
    ww = clamp(10 * bbox["w"], 0.0025, 0.06)
    wh = clamp(4 * bbox["h"], 0.03, 0.6)
    wx = clamp(bbox["x"] + bbox["w"] / 2 - ww / 2, 0.0, 1.0 - ww)
    wy = clamp(bbox["y"] + bbox["h"] / 2 - wh / 2, 0.0, 1.0 - wh)
    cw = clamp(10 * rect["w"], 0.0025, 0.06)
    ch = clamp(4 * rect["h"], 0.03, 0.6)
    cx = clamp(rect["x"] + rect["w"] / 2 - cw / 2, 0.0, 1.0 - cw)
    cy = clamp(rect["y"] + rect["h"] / 2 - ch / 2, 0.0, 1.0 - ch)
    return ([round(v, 5) for v in (wx, wy, ww, wh)],
            [round(v, 5) for v in (cx, cy, cw, ch)])


# ---------------------------------------------------------------------------
# bench
# ---------------------------------------------------------------------------

@router.get("/transfer/bench")
async def bench(target: str, donors: str | None = None):
    async with wb_engine.connect() as conn:
        tgt = (await conn.execute(text(
            "SELECT id, title, width, height, sizes, compass_angle "
            "FROM photo_mirror WHERE id = :id"), {"id": target})).first()
        if not tgt:
            raise HTTPException(404, "target photo not found")
        # donor suggestions: nearby panos with current annotations
        sugg = (await conn.execute(text(
            "SELECT p.id, p.title, p.width, p.height, "
            "count(a.id) FILTER (WHERE a.is_current AND a.missing_since IS NULL) AS n "
            "FROM photo_mirror p JOIN photo_mirror t ON t.id = :tid "
            "LEFT JOIN annotation_mirror a ON a.photo_id = p.id "
            "WHERE p.id != :tid AND p.deleted = false AND p.missing_since IS NULL "
            "AND ST_DWithin(p.geometry::geography, t.geometry::geography, 200) "
            "GROUP BY p.id, p.title, p.width, p.height "
            "HAVING count(a.id) FILTER (WHERE a.is_current AND a.missing_since IS NULL) > 0 "
            "ORDER BY n DESC"), {"tid": target})).all()
    donor_ids = ([d for d in donors.split(",") if d] if donors
                 else [r.id for r in sugg])

    donors_out = []
    all_transfer_ids: list[str] = []
    transfers_by_ann: dict[str, dict] = {}
    if donor_ids:
        async with wb_engine.connect() as conn:
            trows = (await conn.execute(text(
                "SELECT t.* FROM transfers t "
                "JOIN annotation_mirror a ON a.id = t.annotation_id "
                "WHERE t.target_photo_id = :tid AND a.photo_id = ANY(:dids)"),
                {"tid": target, "dids": donor_ids})).all()
        for t in trows:
            transfers_by_ann[t.annotation_id] = dict(t._mapping)
            all_transfer_ids.append(str(t.id))
    results = await _transfer_results(all_transfer_ids)
    dps = await _datapoints(target, tgt.width or 1)

    for did in donor_ids:
        async with wb_engine.connect() as conn:
            ph = (await conn.execute(text(
                "SELECT id, title, width, height, sizes, compass_angle "
                "FROM photo_mirror WHERE id = :id"), {"id": did})).first()
            if not ph:
                continue
            anns = (await conn.execute(text(
                "SELECT id, body, target, origin FROM annotation_mirror "
                "WHERE photo_id = :id AND is_current AND missing_since IS NULL "
                "ORDER BY (target->'selector'->'geometry'->>'x')::float NULLS LAST"),
                {"id": did})).all()
        cal = await _donor_cal(did, ph.compass_angle)
        ann_out = []
        for a in anns:
            rect = _rect_of(a.target)
            az = _azimuth(rect, cal) if (rect and cal) else None
            t = transfers_by_ann.get(a.id)
            entry = {"id": a.id, "body": a.body, "rect": rect, "origin": a.origin,
                     "azimuth": round(az, 2) if az is not None else None,
                     "prediction": _predict(az, dps, tgt.width or 1)
                                   if az is not None else None}
            if t:
                res = results.get(str(t["id"]), [])
                bbox, stage = _proposed(res)
                entry["transfer"] = {
                    "id": str(t["id"]), "status": t["status"],
                    "accepted_annotation_id": t["accepted_annotation_id"],
                    "note": t["note"],
                    "proposed_rect": t["proposed_rect"] or bbox,
                    "proposed_stage": stage,
                    "queued": sum(1 for r in res if r["status"] == "queued"),
                    "results": res}
            ann_out.append(entry)
        donors_out.append({"photo": dict(ph._mapping),
                           "calibration": cal, "annotations": ann_out})

    return {"target": dict(tgt._mapping),
            "donor_suggestions": [dict(r._mapping) for r in sugg],
            "donors": donors_out,
            "datapoints": sorted(dps, key=lambda d: d["az"])}


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------

async def _ensure_transfer(annotation_id: str, target: str) -> dict:
    async with wb_engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO transfers (annotation_id, target_photo_id) "
            "VALUES (:aid, :tid) ON CONFLICT (annotation_id, target_photo_id) "
            "DO NOTHING"), {"aid": annotation_id, "tid": target})
        row = (await conn.execute(text(
            "SELECT * FROM transfers WHERE annotation_id = :aid "
            "AND target_photo_id = :tid"), {"aid": annotation_id, "tid": target})).first()
    return dict(row._mapping)


async def _donor_of(annotation_id: str):
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT a.id, a.body, a.target, a.photo_id, p.compass_angle, p.width "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = :id"), {"id": annotation_id})).first()
    if not row:
        raise HTTPException(404, "annotation not found")
    return row


class CoarseRequest(BaseModel):
    target: str
    annotation_ids: list[str]


@router.post("/transfer/coarse")
async def coarse(req: CoarseRequest):
    async with wb_engine.connect() as conn:
        tw = (await conn.execute(text(
            "SELECT width FROM photo_mirror WHERE id = :id"),
            {"id": req.target})).scalar()
    if not tw:
        raise HTTPException(404, "target photo not found")
    dps = await _datapoints(req.target, tw)
    queued, skipped = [], []
    for aid in req.annotation_ids:
        donor = await _donor_of(aid)
        rect = _rect_of(donor.target)
        cal = await _donor_cal(donor.photo_id, donor.compass_angle)
        if not rect or not cal:
            skipped.append({"annotation_id": aid, "reason": "no rect or bearing"})
            continue
        pred = _predict(_azimuth(rect, cal), dps, tw)
        if not pred:
            skipped.append({"annotation_id": aid,
                            "reason": "no datapoints yet — run a sweep first"})
            continue
        t = await _ensure_transfer(aid, req.target)
        window, context = _coarse_specs(rect, cal, pred, tw)
        rid = await enqueue_pair(aid, req.target, window=window, context=context,
                                 extra_params={"transfer_id": str(t["id"]),
                                               "stage": "coarse"})
        queued.append({"annotation_id": aid, "result_id": rid,
                       "window": window, "context": context})
    return {"queued": queued, "skipped": skipped}


class SweepRequest(BaseModel):
    target: str
    annotation_id: str


@router.post("/transfer/sweep")
async def sweep(req: SweepRequest):
    """Seed the prior: scan the WHOLE target width with one annotation (pick a
    big, distinctive one). The winning window's projection becomes the first
    azimuth↦x datapoint; everything after uses predicted windows."""
    donor = await _donor_of(req.annotation_id)
    rect = _rect_of(donor.target)
    cal = await _donor_cal(donor.photo_id, donor.compass_angle)
    if not rect or not cal:
        raise HTTPException(422, "annotation has no rect or its pano no bearing")
    t = await _ensure_transfer(req.annotation_id, req.target)
    ctx_w = min(COARSE_DEG / cal["fov"], 1.0)
    cx0 = min(max(rect["x"] + rect["w"] / 2 - ctx_w / 2, 0.0), 1.0 - ctx_w)
    context = [round(cx0, 5), 0.0, round(ctx_w, 5), 1.0]
    queued = []
    x = 0.0
    while x < 1.0 - SWEEP_W / 2:
        window = [round(min(x, 1.0 - SWEEP_W), 5), 0.0, SWEEP_W, 1.0]
        rid = await enqueue_pair(req.annotation_id, req.target, window=window,
                                 context=context,
                                 extra_params={"transfer_id": str(t["id"]),
                                               "stage": "sweep"})
        queued.append(rid)
        x += SWEEP_STEP
    return {"transfer_id": str(t["id"]), "queued": len(queued)}


class TransferIdRequest(BaseModel):
    transfer_id: str
    note: str | None = None


@router.post("/transfer/refine")
async def refine(req: TransferIdRequest):
    async with wb_engine.connect() as conn:
        t = (await conn.execute(text(
            "SELECT * FROM transfers WHERE id = CAST(:id AS uuid)"),
            {"id": req.transfer_id})).first()
    if not t:
        raise HTTPException(404, "transfer not found")
    res = (await _transfer_results([str(t.id)])).get(str(t.id), [])
    best = _best(res, ("coarse", "sweep"))
    if not best or best["h_inliers"] < CONF_INLIERS:
        raise HTTPException(422, "no confident coarse result to refine from")
    donor = await _donor_of(t.annotation_id)
    rect = _rect_of(donor.target)
    window, context = _refine_specs(rect, best["bbox"])
    rid = await enqueue_pair(t.annotation_id, t.target_photo_id, window=window,
                             context=context,
                             extra_params={"transfer_id": str(t.id),
                                           "stage": "refine"})
    return {"result_id": rid, "window": window, "context": context}


class AcceptRequest(BaseModel):
    transfer_id: str
    rect: dict | None = None       # nudged {x,y,w,h}; defaults to the proposal
    poi: bool = True               # relate/mint a shared POI
    poi_label: str | None = None


@router.post("/transfer/accept")
async def accept(req: AcceptRequest):
    async with wb_engine.connect() as conn:
        t = (await conn.execute(text(
            "SELECT * FROM transfers WHERE id = CAST(:id AS uuid)"),
            {"id": req.transfer_id})).first()
    if not t:
        raise HTTPException(404, "transfer not found")
    donor = await _donor_of(t.annotation_id)
    rect = req.rect
    if not rect:
        res = (await _transfer_results([str(t.id)])).get(str(t.id), [])
        rect, _ = _proposed(res)
    if not rect:
        raise HTTPException(422, "no proposed rect — run coarse/refine first, or pass one")
    rect = {k: round(float(rect[k]), 6) for k in ("x", "y", "w", "h")}
    target_dict = {"selector": {"type": "RECTANGLE", "geometry": dict(rect)}}

    run_id = await create_run(kind="transfer_accept", params={
        "transfer_id": str(t.id), "annotation_id": t.annotation_id,
        "target_photo_id": t.target_photo_id, "rect": rect})
    try:
        if t.accepted_annotation_id:
            # re-accept after reopen: move the existing native annotation
            async with wb_engine.begin() as conn:
                await conn.execute(text(
                    "UPDATE annotation_mirror SET target = CAST(:tg AS jsonb) "
                    "WHERE id = :id AND origin = 'workbench'"),
                    {"tg": json.dumps(target_dict), "id": t.accepted_annotation_id})
            new_id = t.accepted_annotation_id
        else:
            created = await create_native_annotation(NativeAnnotationCreate(
                photo_id=t.target_photo_id, body=donor.body, target=target_dict))
            new_id = created["id"]
            # provenance: the clone derives from the donor annotation
            new_iri = facts.iri(graph.annotation_iri(new_id))
            donor_iri = facts.iri(graph.annotation_iri(t.annotation_id))
            await _mint_approved(
                [((new_iri, facts._p("derivedFrom"), donor_iri),
                  graph.annotation_iri(new_id))], run_id)

        poi_id = None
        if req.poi:
            res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?poi WHERE {{
  GRAPH ?f {{ <{graph.annotation_iri(t.annotation_id)}> hv:depicts ?poi }}
  GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status hv:approved }}
}}""")
            found = [b["poi"]["value"] for b in res["results"]["bindings"]]
            if found:
                poi_id = found[0].rsplit("/", 1)[-1]
                await relate_annotation(poi_id, RelateRequest(annotation_id=new_id))
            else:
                out = await create_poi(CreatePoiRequest(
                    label=req.poi_label or parse_body(donor.body).name,
                    annotation_ids=[t.annotation_id, new_id]))
                poi_id = out["poi_id"]

        async with wb_engine.begin() as conn:
            await conn.execute(text(
                "UPDATE transfers SET status = 'accepted', "
                "accepted_annotation_id = :nid, proposed_rect = CAST(:r AS jsonb), "
                "updated_at = now() WHERE id = CAST(:id AS uuid)"),
                {"nid": new_id, "r": json.dumps(rect), "id": str(t.id)})
        await finish_run(run_id, stats={"annotation_id": new_id, "poi_id": poi_id})
        return {"annotation_id": new_id, "poi_id": poi_id, "rect": rect}
    except HTTPException:
        await fail_run(run_id, "downstream HTTP error")
        raise
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"accept failed: {e}")


@router.post("/transfer/reject")
async def reject(req: TransferIdRequest):
    async with wb_engine.begin() as conn:
        n = (await conn.execute(text(
            "UPDATE transfers SET status = 'rejected', note = :n, updated_at = now() "
            "WHERE id = CAST(:id AS uuid) RETURNING id"),
            {"n": req.note, "id": req.transfer_id})).first()
    if not n:
        raise HTTPException(404, "transfer not found")
    return {"status": "rejected"}


@router.post("/transfer/reopen")
async def reopen(req: TransferIdRequest):
    """Back to open. An already-created native annotation stays (re-accept
    updates it in place; delete it via the photo page if truly unwanted)."""
    async with wb_engine.begin() as conn:
        n = (await conn.execute(text(
            "UPDATE transfers SET status = 'open', updated_at = now() "
            "WHERE id = CAST(:id AS uuid) RETURNING id"),
            {"id": req.transfer_id})).first()
    if not n:
        raise HTTPException(404, "transfer not found")
    return {"status": "open"}
