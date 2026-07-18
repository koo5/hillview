"""Proto-annotations: the reverse POI-placement workflow.

The calibration model run backwards: instead of anchors + rect-x → fit, take a POI
with known coordinates (Wikipedia page) and a pano's accepted calibration, and predict
WHERE on the strip it should appear:

    azimuth = bearing(pano → POI)
    x       = 0.5 + ang_norm(azimuth − centre_bearing) / fov      (± rms/fov)

POST /api/panos/{photo_id}/place_poi   — preview (save=false) or mint proto facts
GET  /api/panos/{photo_id}/protos      — existing proto-annotations w/ curation status

A proto-annotation is pure facts (no table): subject /id/proto-annotation/{hash16},
hash16 = sha256(photo_id|wiki_url)[:16] → idempotent per (pano, POI). The wiki-page
coords triple content-addresses to the SAME fact graph the geocode bench mints, so
the two workflows corroborate each other for free.
"""
import hashlib
import re
import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import calibrate, facts, geocode, graph
from ..db import wb_engine
from ..geocode import wikipedia_coords
from ..runs import create_run, fail_run, finish_run

router = APIRouter()

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
PROTO_PREFIX = f"{graph.BASE}/id/proto-annotation/"


async def _load_photo(photo_id: str):
    async with wb_engine.connect() as conn:
        photo = (await conn.execute(text(
            "SELECT id, title, width, height, compass_angle, sizes, "
            "ST_X(geometry) AS lon, ST_Y(geometry) AS lat "
            "FROM photo_mirror WHERE id = :id"), {"id": photo_id})).first()
    if not photo:
        raise HTTPException(404, "photo not found")
    return photo


async def _calibration_for(photo_id: str) -> dict | None:
    """Pick the pano's effective calibration from the fact store.

    Each accept run emits bearing+fov+rms together, so group facts by generating
    run; drop rejected facts; prefer a run with any approved fact, else the most
    recent run (started_at from the runs table). → {centre_bearing, fov, rms,
    run_id, approved} | None."""
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?p ?v ?run ?status WHERE {{
  GRAPH ?f {{ <{graph.photo_iri(photo_id)}> ?p ?v }}
  VALUES ?p {{ hv:calibratedBearing hv:calibratedFov hv:calibrationRms }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_META}> {{ ?f prov:wasGeneratedBy ?run }} }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    by_run: dict[str, dict] = {}
    for b in res["results"]["bindings"]:
        status = b.get("status", {}).get("value", "")
        if status.endswith("rejected"):
            continue
        run = b.get("run", {}).get("value", "")
        d = by_run.setdefault(run, {"approved": False})
        d[b["p"]["value"].rsplit("#", 1)[-1]] = float(b["v"]["value"])
        if status.endswith("approved"):
            d["approved"] = True
    complete = {r: d for r, d in by_run.items()
                if "calibratedBearing" in d and "calibratedFov" in d}
    if not complete:
        return None
    run_ids = [r.rsplit("/", 1)[-1] for r in complete]
    order: dict[str, int] = {}
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id FROM runs WHERE id = ANY(CAST(:ids AS uuid[])) "
            "ORDER BY started_at"), {"ids": run_ids})).all()
    for i, (rid,) in enumerate(rows):
        order[str(rid)] = i
    best = max(complete.items(),
               key=lambda kv: (kv[1]["approved"],
                               order.get(kv[0].rsplit("/", 1)[-1], -1)))
    d = best[1]
    return {"centre_bearing": d["calibratedBearing"], "fov": d["calibratedFov"],
            "rms": d.get("calibrationRms"), "run": best[0],
            "approved": d["approved"]}


class PlacePoiRequest(BaseModel):
    wikipedia_url: str
    save: bool = False
    # fallback FOV (deg) for panos without an accepted calibration — x is then a
    # compass-only estimate (bias unknown), flagged calibrated=false
    assumed_fov: float | None = None
    note: str | None = None


@router.post("/panos/{photo_id}/place_poi")
async def place_poi(photo_id: str, req: PlacePoiRequest):
    try:
        lang, raw_title, wiki_url, label = geocode.parse_wikipedia_url(req.wikipedia_url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    title = urllib.parse.unquote(raw_title)

    photo = await _load_photo(photo_id)
    if photo.lat is None:
        raise HTTPException(422, "photo has no position")

    poi = await wikipedia_coords(lang, title)
    if not poi:
        raise HTTPException(422, f"no coordinates on {lang}:{label} "
                                 "(page missing them, or the lookup failed — retry once)")

    azimuth = calibrate.bearing_deg(photo.lon, photo.lat, poi["lon"], poi["lat"])
    km = calibrate.haversine_km(photo.lon, photo.lat, poi["lon"], poi["lat"])
    delta = (calibrate.ang_norm(azimuth - photo.compass_angle)
             if photo.compass_angle is not None else None)

    cal = await _calibration_for(photo_id)
    x = x_err = None
    if cal:
        x = 0.5 + calibrate.ang_norm(azimuth - cal["centre_bearing"]) / cal["fov"]
        if cal.get("rms") is not None:
            x_err = cal["rms"] / cal["fov"]
    elif req.assumed_fov and delta is not None:
        x = 0.5 + delta / req.assumed_fov

    out = {
        "photo_id": photo_id, "wikipedia_url": wiki_url, "label": label,
        "poi": poi, "azimuth": round(azimuth, 2), "km": round(km, 2),
        "delta_vs_compass": round(delta, 2) if delta is not None else None,
        "calibration": cal, "calibrated": cal is not None,
        "x": round(x, 4) if x is not None else None,
        "x_error": round(x_err, 4) if x_err is not None else None,
        "in_frame": (0.0 <= x <= 1.0) if x is not None else None,
        # signed degrees past the nearer edge (negative = off the left)
        "off_frame_deg": (round((x if x < 0 else x - 1) * (cal or {}).get("fov", req.assumed_fov or 0), 1)
                          if x is not None and not 0.0 <= x <= 1.0 else None),
        "saved": None,
    }
    if not req.save:
        return out
    if x is None:
        raise HTTPException(422, "nothing to save: no calibration and no assumed_fov → no x")

    proto_hash = hashlib.sha256(f"{photo_id}|{wiki_url}".encode()).hexdigest()[:16]
    proto = facts.iri(graph.proto_annotation_iri(proto_hash))
    triples = [
        (proto, facts.iri(RDF_TYPE), facts._p("ProtoAnnotation")),
        (proto, facts._p("onPhoto"), facts.iri(graph.photo_iri(photo_id))),
        (proto, facts._p("labelText"), facts.lit(label)),
        (proto, facts._p("wikipediaPage"), facts.iri(wiki_url)),
        (proto, facts._p("assumedX"), facts.lit(str(round(x, 4)), facts.XSD + "double")),
        # same triple the geocode bench mints for wiki candidates → same fact graph
        (facts.iri(wiki_url), facts._p("coords"),
         facts.lit(f"POINT({poi['lon']} {poi['lat']})", f"{facts.GEO}wktLiteral")),
    ]
    if x_err is not None:
        triples.append((proto, facts._p("assumedXError"),
                        facts.lit(str(round(x_err, 4)), facts.XSD + "double")))

    run_id = await create_run(
        kind="place_poi",
        params={"photo_id": photo_id, "wikipedia_url": wiki_url, "poi": poi,
                "x": out["x"], "x_error": out["x_error"],
                "calibration_run": (cal or {}).get("run"),
                "assumed_fov": req.assumed_fov},
        note=req.note)
    try:
        fact_graphs: dict[str, str] = {}
        meta_lines = []
        run = graph.run_iri(run_id)
        for s, p, o in triples:
            h = facts.fact_hash(s, p, o)
            g = graph.fact_iri(h)
            fact_graphs[g] = f"{s} {p} {o} .\n"
            meta_lines.append(f"{facts.iri(g)} <http://www.w3.org/ns/prov#wasGeneratedBy> {facts.iri(run)} .")
            meta_lines.append(f"{facts.iri(g)} {facts._p('about')} {proto} .")
        for g_iri, nt in fact_graphs.items():
            await graph.store.load_turtle(g_iri, nt)
        await graph.store.load_turtle(graph.GRAPH_META,
                                      graph.PREFIXES + "\n" + "\n".join(meta_lines))
        await finish_run(run_id, stats={"facts": len(fact_graphs)},
                         graph_iri=graph.run_iri(run_id))
        out["saved"] = {"run_id": str(run_id),
                        "proto": graph.proto_annotation_iri(proto_hash),
                        "facts": len(fact_graphs)}
        return out
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"place_poi save failed: {e}")


@router.get("/panos/{photo_id}/protos")
async def list_protos(photo_id: str):
    """Proto-annotations placed on this pano, with per-fact curation status
    (rows shaped for FactChip: fact/predicate/value/value_type/datatype/status)."""
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?proto ?p ?v ?f ?status WHERE {{
  GRAPH ?fp {{ ?proto hv:onPhoto <{graph.photo_iri(photo_id)}> }}
  FILTER STRSTARTS(STR(?proto), "{PROTO_PREFIX}")
  GRAPH ?f {{ ?proto ?p ?v }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    protos: dict[str, dict] = {}
    for b in res["results"]["bindings"]:
        iri = b["proto"]["value"]
        d = protos.setdefault(iri, {"proto": iri, "label": None, "wikipedia_url": None,
                                    "x": None, "x_error": None, "facts": []})
        pred = b["p"]["value"].rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        val, vtype = b["v"]["value"], b["v"]["type"]
        status = b.get("status", {}).get("value", "")
        d["facts"].append({
            "fact": b["f"]["value"], "predicate": pred, "value": val,
            "value_type": "uri" if vtype == "uri" else "literal",
            "datatype": b["v"].get("datatype"),
            "status": status.rsplit("#", 1)[-1] if status else "proposed"})
        if pred == "labelText":
            d["label"] = val
        elif pred == "wikipediaPage":
            d["wikipedia_url"] = val
        elif pred == "assumedX":
            d["x"] = float(val)
            d["x_status"] = d["facts"][-1]["status"]
        elif pred == "assumedXError":
            d["x_error"] = float(val)
    return sorted(protos.values(), key=lambda d: (d["x"] is None, d["x"]))
