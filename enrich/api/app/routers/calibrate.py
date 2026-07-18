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

    rows = []
    for a in anns:
        rx = _rect_x(a.target)
        cand_data = await candidates_endpoint(a.id)
        chosen, rule = calibrate.pick_anchor(
            cand_data["candidates"], photo.lon, photo.lat, photo.compass_angle,
            importance)
        row = {"annotation_id": a.id, "body": (a.body or "")[:60], "rect_x": rx,
               "rule": rule, "anchor": None, "azimuth": None, "delta": None,
               "km": None, "usable": False}
        if chosen and rx is not None and photo.lat is not None:
            az = calibrate.bearing_deg(photo.lon, photo.lat, chosen["lon"], chosen["lat"])
            km = calibrate.haversine_km(photo.lon, photo.lat, chosen["lon"], chosen["lat"])
            delta = (calibrate.ang_norm(az - photo.compass_angle)
                     if photo.compass_angle is not None else None)
            row.update({"anchor": chosen, "azimuth": round(az, 2), "km": round(km, 2),
                        "delta": round(delta, 2) if delta is not None else None,
                        "usable": delta is not None and km >= calibrate.MIN_KM})
        rows.append(row)
    return {"photo": dict(photo._mapping), "rows": rows}


@router.get("/panos/{photo_id}/calibration")
async def calibration(photo_id: str):
    data = await _calibration_rows(photo_id)
    usable = [{"x": r["rect_x"], "delta": r["delta"]}
              for r in data["rows"] if r["usable"]]
    data["fit"] = calibrate.fit_summary(usable, data["photo"]["compass_angle"])
    return data


class AcceptRequest(BaseModel):
    photo_id: str
    annotation_ids: list[str]      # the INCLUDED set (UI's toggles, authoritative)
    note: str | None = None


@router.post("/calibrate/accept")
async def accept(req: AcceptRequest):
    data = await _calibration_rows(req.photo_id)
    included = [r for r in data["rows"]
                if r["usable"] and r["annotation_id"] in set(req.annotation_ids)]
    pts = [{"x": r["rect_x"], "delta": r["delta"]} for r in included]
    fit = calibrate.fit_summary(pts, data["photo"]["compass_angle"])
    if not fit:
        raise HTTPException(422, "need at least 2 usable included anchors")

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
