"""Calibration bench API.

GET  /api/panos                        — panos (aspect ≥ 2) + annotation/anchor counts
GET  /api/panos/{photo_id}/calibration — per-annotation calibration rows (rect_x,
                                         chosen anchor + rule, azimuth, delta) + photo
POST /api/calibrate/accept             — server-side Theil-Sen refit over the included
                                         annotations → calibration facts (run-tracked)
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import calibrate, facts, graph
from ..db import wb_engine
from ..runs import create_run, fail_run, finish_run
from .geocode import candidates as candidates_endpoint

router = APIRouter()

PANO_WHERE = ("p.deleted = false AND p.missing_since IS NULL AND "
              "greatest(p.width, p.height)::float / nullif(least(p.width, p.height), 0) >= 2.0")


@router.get("/panos")
async def list_panos():
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT p.id, p.title, p.width, p.height, p.compass_angle, p.sizes, "
            f"ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat, "
            f"count(a.id) FILTER (WHERE a.is_current AND a.missing_since IS NULL) AS n_annotations "
            f"FROM photo_mirror p "
            f"LEFT JOIN annotation_mirror a ON a.photo_id = p.id "
            f"WHERE {PANO_WHERE} "
            f"GROUP BY p.id ORDER BY n_annotations DESC"))).all()
    # which panos already carry calibration facts?
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT DISTINCT ?ph WHERE {{ GRAPH ?f {{ ?ph hv:calibratedBearing ?o }} }}""")
    calibrated = {b["ph"]["value"].rsplit("/", 1)[-1]
                  for b in res["results"]["bindings"]}
    return [{**dict(r._mapping), "calibrated": r.id in calibrated} for r in rows]


def _rect_x(target) -> float | None:
    try:
        g = (target.get("selector") or {}).get("geometry") or {}
        x, w = float(g["x"]), float(g.get("w", 0))
        if 0 <= x <= 1 and 0 < w <= 1:
            return x + w / 2
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return None


async def _calibration_rows(photo_id: str) -> dict:
    async with wb_engine.connect() as conn:
        photo = (await conn.execute(text(
            "SELECT id, title, width, height, compass_angle, sizes, "
            "ST_X(geometry) AS lon, ST_Y(geometry) AS lat "
            "FROM photo_mirror WHERE id = :id"), {"id": photo_id})).first()
        if not photo:
            raise HTTPException(404, "photo not found")
        anns = (await conn.execute(text(
            "SELECT id, body, target FROM annotation_mirror "
            "WHERE photo_id = :id AND is_current AND missing_since IS NULL"),
            {"id": photo_id})).all()

    # cached nominatim importance, keyed by candidate OSM URI (per label query)
    async with wb_engine.connect() as conn:
        imp_rows = (await conn.execute(text(
            "SELECT result FROM geocode_cache WHERE kind = 'nominatim'"))).all()
    importance: dict[str, float] = {}
    for (result,) in imp_rows:
        if isinstance(result, list):
            for c in result:
                uri = f"https://www.openstreetmap.org/{c.get('osm_type')}/{c.get('osm_id')}"
                importance[uri] = max(importance.get(uri, 0.0),
                                      float(c.get("importance") or 0))

    # pass 1: each annotation's own candidates. Trusted picks (approved / pinned
    # / wikipedia) then teach the auto-picker where a rect x should point: the
    # pano's accepted calibration if it has one, else a Theil-Sen fit over ≥3
    # trusted rows, else a compass window widened by the aspect ratio. Every
    # row carries `why`, shown on the bench next to the rule.
    cands_by_ann = {a.id: (await candidates_endpoint(a.id))["candidates"] for a in anns}
    # a rect reshaped in the workbench (approved proposedGeometry) counts here
    # too — otherwise the bench keeps measuring the old rect
    from ..geometry import effective_targets
    targets = await effective_targets(anns)

    def geom(chosen):
        az = calibrate.bearing_deg(photo.lon, photo.lat, chosen["lon"], chosen["lat"])
        km = calibrate.haversine_km(photo.lon, photo.lat, chosen["lon"], chosen["lat"])
        delta = (calibrate.ang_norm(az - photo.compass_angle)
                 if photo.compass_angle is not None else None)
        return az, km, delta

    trusted = []
    for a in anns:
        rx = _rect_x(targets[a.id])
        chosen, rule, _ = calibrate.pick_anchor(cands_by_ann[a.id], photo.lon, photo.lat,
                                                photo.compass_angle, importance)
        if chosen and rule in ("approved", "pinned", "wikipedia") and rx is not None \
                and photo.lat is not None:
            _, km, delta = geom(chosen)
            if delta is not None and km >= calibrate.MIN_KM:
                trusted.append({"x": rx, "delta": delta})

    predict, predict_basis = None, ""
    from .proto import _calibration_for
    cal = await _calibration_for(photo_id) if photo.compass_angle is not None else None
    if cal and cal.get("centre_bearing") is not None and cal.get("fov"):
        cb, fov = float(cal["centre_bearing"]), float(cal["fov"])
        predict = lambda x, cb=cb, fov=fov: calibrate.ang_norm(  # noqa: E731
            cb - photo.compass_angle + fov * (x - 0.5))
        predict_basis = (f"{'approved' if cal.get('approved') else 'latest'} calibration, "
                         f"FOV {fov:.0f}°")
    elif len(trusted) >= 3 and photo.compass_angle is not None:
        calibrate.unwrap_deltas(trusted, photo.width, photo.height)  # aspect prior: no calibration here
        fit = calibrate.theil_sen([t["x"] for t in trusted], [t["delta"] for t in trusted])
        if fit:
            a0, b0 = fit
            predict = lambda x, a0=a0, b0=b0: a0 + b0 * x  # noqa: E731
            predict_basis = f"fit of {len(trusted)} trusted anchors, FOV {abs(b0):.0f}°"
    half, window_basis = calibrate.half_window_for(photo.width, photo.height)

    rows = []
    for a in anns:
        rx = _rect_x(targets[a.id])
        chosen, rule, why = calibrate.pick_anchor(
            cands_by_ann[a.id], photo.lon, photo.lat, photo.compass_angle,
            importance, rect_x=rx, predict=predict, predict_basis=predict_basis,
            half_window=half, window_basis=window_basis)
        row = {"annotation_id": a.id, "body": (a.body or "")[:60], "rect_x": rx,
               "rule": rule, "why": why, "anchor": None, "azimuth": None,
               "delta": None, "km": None, "usable": False}
        if chosen and rx is not None and photo.lat is not None:
            az, km, delta = geom(chosen)
            row.update({"anchor": chosen, "azimuth": round(az, 2), "km": round(km, 2),
                        "delta": round(delta, 2) if delta is not None else None,
                        "usable": delta is not None and km >= calibrate.MIN_KM})
        elif chosen and rx is None:
            row["why"] += "; the rect has no usable x"
        rows.append(row)
    return {"photo": dict(photo._mapping), "rows": rows}


@router.get("/panos/{photo_id}/calibration")
async def calibration(photo_id: str):
    data = await _calibration_rows(photo_id)
    usable = [{"x": r["rect_x"], "delta": r["delta"]}
              for r in data["rows"] if r["usable"]]
    photo = data["photo"]
    prior = await _unwrap_prior(photo_id)
    n_unwrapped = calibrate.unwrap_deltas(usable, photo.get("width"), photo.get("height"), prior)
    data["fit"] = calibrate.fit_summary(usable, photo["compass_angle"])
    if data["fit"]:
        data["fit"]["unwrapped"] = n_unwrapped
    # the bench mirrors the unwrap client-side (live toggle-and-refit) with the
    # same prior, so both sides agree on which Δ crossed ±180
    data["unwrap_prior_fov"] = prior
    # the calibration this pano currently HAS (facts) — the bench seeds its
    # model/seams from it instead of resetting to linear on every visit
    from .proto import _calibration_for
    data["accepted"] = await _calibration_for(photo_id)
    return data


async def _unwrap_prior(photo_id: str) -> float | None:
    """FOV prior for unwrapping Δ: the pano's accepted calibration if it has
    one (None → the aspect-ratio guess inside unwrap_deltas)."""
    from .proto import _calibration_for
    cal = await _calibration_for(photo_id)
    return float(cal["fov"]) if cal and cal.get("fov") else None


class AcceptRequest(BaseModel):
    photo_id: str
    annotation_ids: list[str]      # the INCLUDED set (UI's toggles, authoritative)
    model: str = "linear"          # linear (f1/f2) | rectilinear (f0) | piecewise (stitched)
    # piecewise: seam positions as fractions of the width — the panels between
    # them get their own shift & scale on top of the linear law
    seams: list[float] = []
    note: str | None = None


@router.post("/calibrate/accept")
async def accept(req: AcceptRequest):
    data = await _calibration_rows(req.photo_id)
    included = [r for r in data["rows"]
                if r["usable"] and r["annotation_id"] in set(req.annotation_ids)]
    pts = [{"x": r["rect_x"], "delta": r["delta"]} for r in included]
    n_unwrapped = calibrate.unwrap_deltas(pts, data["photo"].get("width"),
                                          data["photo"].get("height"),
                                          await _unwrap_prior(req.photo_id))
    if req.model == "rectilinear":
        fit = calibrate.fit_rectilinear(pts, data["photo"]["compass_angle"])
        if not fit:
            raise HTTPException(422, "rectilinear needs at least 4 usable included anchors")
    elif req.model == "linear":
        fit = calibrate.fit_summary(pts, data["photo"]["compass_angle"])
        if not fit:
            raise HTTPException(422, "need at least 2 usable included anchors")
    elif req.model == "piecewise":
        fit = calibrate.fit_piecewise(pts, data["photo"]["compass_angle"], req.seams)
        if not fit:
            raise HTTPException(422, "need at least 2 usable included anchors")
    else:
        raise HTTPException(422, "unknown model")
    fit["unwrapped"] = n_unwrapped

    run_id = await create_run(
        kind="calibration",
        params={"photo_id": req.photo_id,
                "included": [r["annotation_id"] for r in included],
                "anchors": [{"annotation": r["annotation_id"],
                             "candidate": r["anchor"]["candidate"],
                             "rule": r["rule"]} for r in included],
                "fit": fit},
        note=req.note)
    try:
        ph = facts.iri(graph.photo_iri(req.photo_id))
        triples = []
        if fit["centre_bearing"] is not None:
            triples.append((ph, facts._p("calibratedBearing"),
                            facts.lit(str(fit["centre_bearing"]),
                                      facts.XSD + "double")))
        triples.append((ph, facts._p("calibratedFov"),
                        facts.lit(str(fit["fov"]), facts.XSD + "double")))
        triples.append((ph, facts._p("calibrationRms"),
                        facts.lit(str(fit["rms"]), facts.XSD + "double")))
        if fit.get("model") == "rectilinear":
            # azimuth↔x law is atan about x0, not linear — consumers that
            # only need centre bearing + span can ignore these two
            triples.append((ph, facts._p("calibratedProjection"),
                            facts.lit("rectilinear")))
            triples.append((ph, facts._p("calibratedX0"),
                            facts.lit(str(fit["x0"]), facts.XSD + "double")))
        if fit.get("model") == "piecewise":
            # the stitch model on top of the linear law: seams + per-panel
            # shift/scale, one JSON literal (the overlay bench's knots/hwarp/
            # hscale, verbatim) — consumers that only need the pie ignore it
            triples.append((ph, facts._p("calibratedStitch"),
                            facts.lit(json.dumps({"knots": fit["knots"],
                                                  "hwarp": fit["hwarp"],
                                                  "hscale": fit["hscale"]},
                                                 separators=(",", ":")))))
        # meta links facts to the pano's annotations? No — hv:about the photo's
        # annotation set is indirect; link to the photo via hv:about instead.
        fact_graphs: dict[str, str] = {}
        meta_lines = []
        run = graph.run_iri(run_id)
        for s, p, o in triples:
            h = facts.fact_hash(s, p, o)
            g = graph.fact_iri(h)
            fact_graphs[g] = f"{s} {p} {o} .\n"
            meta_lines.append(f"{facts.iri(g)} <http://www.w3.org/ns/prov#wasGeneratedBy> {facts.iri(run)} .")
            meta_lines.append(f"{facts.iri(g)} {facts._p('about')} {ph} .")
        for g_iri, nt in fact_graphs.items():
            await graph.store.load_turtle(g_iri, nt)
        await graph.store.load_turtle(graph.GRAPH_META,
                                      graph.PREFIXES + "\n" + "\n".join(meta_lines))
        await finish_run(run_id, stats={"facts": len(fact_graphs), **fit},
                         graph_iri=graph.run_iri(run_id))
        return {"run_id": str(run_id), "fit": fit, "facts": len(fact_graphs)}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"calibration accept failed: {e}")


# ---------------------------------------------------------------------------
# selection draft: the bench's include/exclude working set, as plain MUTABLE
# RDF in a per-pano draft graph (not content-addressed facts — it's working
# state, replaced wholesale on every save; last write wins). Server-side so
# the draft survives browser/device switches.
# ---------------------------------------------------------------------------

def _draft_graph(photo_id: str) -> str:
    return f"{graph.BASE}/id/graph/draft/calibration/{photo_id}"


@router.get("/calibrate/draft")
async def get_calibration_draft(photo_id: str):
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?a WHERE {{
  GRAPH <{_draft_graph(photo_id)}> {{ ?ph hv:calibrationDraftExcludes ?a }}
}}""")
    excluded = [b["a"]["value"].rsplit("/", 1)[-1]
                for b in res["results"]["bindings"]]
    return {"excluded": excluded}


class DraftRequest(BaseModel):
    photo_id: str
    excluded: list[str]


@router.put("/calibrate/draft")
async def put_calibration_draft(req: DraftRequest):
    g = _draft_graph(req.photo_id)
    await graph.store.update(f"DROP SILENT GRAPH <{g}>")
    if req.excluded:
        ph = facts.iri(graph.photo_iri(req.photo_id))
        nt = "".join(
            f"{ph} {facts._p('calibrationDraftExcludes')} "
            f"{facts.iri(graph.annotation_iri(a))} .\n"
            for a in req.excluded)
        await graph.store.load_turtle(g, nt)
    return {"excluded": req.excluded}
