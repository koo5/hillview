"""Points of Interest: the abstract subject that several annotations depict.

The relation is `annotation hv:depicts poi` (one plain triple per pairing, in its
own content-addressed graph — no RDF-star, no metadata-on-triples). A POI is a
first-class node (uuid IRI) so its LABEL and its TRIANGULATED location hang off
it, not off any one annotation, and it scales to N depicting annotations. This is
the enabling model for triangulation: relate the annotations once, then compute
the sight-ray intersection from the POI.

POST /api/pois                      — mint a POI (+ optional label, + relate anns)
POST /api/pois/{id}/annotations     — relate one more annotation
GET  /api/pois                      — list POIs (label + depicting annotations)
GET  /api/pois/{id}                 — detail: annotations, sight-rays, triangulation
"""
import uuid as uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import facts, graph, triangulate
from ..db import wb_engine
from ..runs import create_run, fail_run, finish_run

router = APIRouter()

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
POI_CLASS = f"{graph.NS}PointOfInterest"


async def _mint_approved(triples_about: list[tuple], run_id) -> list[str]:
    """triples_about: [((s_nt, p_nt, o_nt), about_iri)]. Mint each as a
    content-addressed graph + meta (wasGeneratedBy + about) and approve it (a POI
    relation is a user assertion). → the fact-graph IRIs."""
    run = facts.iri(graph.run_iri(run_id))
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for (s, p, o), about in triples_about:
        g = graph.fact_iri(facts.fact_hash(s, p, o))
        await graph.store.load_turtle(g, f"{s} {p} {o} .\n")
        await graph.store.load_turtle(
            graph.GRAPH_META,
            f"{facts.iri(g)} <http://www.w3.org/ns/prov#wasGeneratedBy> {run} .\n"
            f"{facts.iri(g)} {facts._p('about')} {facts.iri(about)} .\n")
        await graph.store.update(facts.curate_update(g, "approved", now))
        out.append(g)
    return out


async def _annotation_ray(ann_id: str) -> dict | None:
    """The annotation's sight ray: pano position + azimuth (calibrated rect-x when
    the pano has a fit, else compass ± assumed FOV). None if it can't be formed."""
    from ..calibrate import rect_x
    from .proto import _calibration_for
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT a.target, a.photo_id, a.body, ST_X(p.geometry) AS lon, "
            "ST_Y(p.geometry) AS lat, p.compass_angle, p.title "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = :id"), {"id": ann_id})).first()
    if not row or row.lat is None:
        return None
    rx = rect_x(row.target)
    if rx is None:
        return None
    cal = await _calibration_for(row.photo_id)
    if cal:
        az = (cal["centre_bearing"] + (rx - 0.5) * cal["fov"]) % 360
    elif row.compass_angle is not None:
        az = (row.compass_angle + (rx - 0.5) * 90.0) % 360
    else:
        return None
    return {"annotation_id": ann_id, "photo_id": row.photo_id,
            "body": row.body, "photo_title": row.title,
            "lat": row.lat, "lon": row.lon, "azimuth": round(az, 2),
            "calibrated": cal is not None}


class CreatePoiRequest(BaseModel):
    label: str | None = None
    annotation_ids: list[str] = []


@router.post("/pois")
async def create_poi(req: CreatePoiRequest):
    poi_id = str(uuid_mod.uuid4())
    poi = facts.iri(graph.poi_iri(poi_id))
    triples: list[tuple] = [((poi, facts.iri(RDF_TYPE), facts.iri(POI_CLASS)),
                             graph.poi_iri(poi_id))]
    if req.label and req.label.strip():
        triples.append(((poi, facts._p("label"), facts.lit(req.label.strip())),
                        graph.poi_iri(poi_id)))
    for aid in req.annotation_ids:
        ann = facts.iri(graph.annotation_iri(aid))
        # `about` the annotation → the relation also surfaces on its detail page
        triples.append(((ann, facts._p("depicts"), poi), graph.annotation_iri(aid)))

    run_id = await create_run(kind="poi", params={"poi_id": poi_id,
                                                  "label": req.label,
                                                  "annotation_ids": req.annotation_ids})
    try:
        await _mint_approved(triples, run_id)
        await finish_run(run_id, stats={"poi_id": poi_id, "annotations": len(req.annotation_ids)})
        return {"poi_id": poi_id, "poi": graph.poi_iri(poi_id), "label": req.label}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"poi create failed: {e}")


class RelateRequest(BaseModel):
    annotation_id: str


@router.post("/pois/{poi_id}/annotations")
async def relate_annotation(poi_id: str, req: RelateRequest):
    poi = facts.iri(graph.poi_iri(poi_id))
    async with wb_engine.connect() as conn:
        ok = (await conn.execute(text(
            "SELECT 1 FROM annotation_mirror WHERE id = :id"),
            {"id": req.annotation_id})).first()
    if not ok:
        raise HTTPException(404, "annotation not found")
    ann = facts.iri(graph.annotation_iri(req.annotation_id))
    run_id = await create_run(kind="poi_relate",
                              params={"poi_id": poi_id, "annotation_id": req.annotation_id})
    try:
        await _mint_approved(
            [((ann, facts._p("depicts"), poi), graph.annotation_iri(req.annotation_id))],
            run_id)
        await finish_run(run_id, stats={"poi_id": poi_id})
        return {"poi_id": poi_id, "annotation_id": req.annotation_id}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"relate failed: {e}")


@router.get("/pois")
async def list_pois():
    """Every approved POI with its label and the annotations depicting it."""
    poi_prefix = graph.poi_iri("")
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?poi ?label (COUNT(DISTINCT ?ann) AS ?n) WHERE {{
  GRAPH ?tf {{ ?poi <{RDF_TYPE}> <{POI_CLASS}> }}
  GRAPH <{graph.GRAPH_CURATION}> {{ ?tf hv:status hv:approved }}
  OPTIONAL {{
    GRAPH ?lf {{ ?poi hv:label ?label }}
    GRAPH <{graph.GRAPH_CURATION}> {{ ?lf hv:status hv:approved }}
  }}
  OPTIONAL {{
    GRAPH ?df {{ ?ann hv:depicts ?poi }}
    GRAPH <{graph.GRAPH_CURATION}> {{ ?df hv:status hv:approved }}
  }}
}} GROUP BY ?poi ?label ORDER BY ?label""")
    out = []
    for b in res["results"]["bindings"]:
        out.append({"poi_id": b["poi"]["value"][len(poi_prefix):],
                    "label": b.get("label", {}).get("value"),
                    "n_annotations": int(b["n"]["value"])})
    return {"pois": out}


@router.get("/pois/{poi_id}")
async def poi_detail(poi_id: str):
    poi = graph.poi_iri(poi_id)
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?ann ?label WHERE {{
  {{
    GRAPH ?df {{ ?ann hv:depicts <{poi}> }}
    GRAPH <{graph.GRAPH_CURATION}> {{ ?df hv:status hv:approved }}
  }} UNION {{
    GRAPH ?lf {{ <{poi}> hv:label ?label }}
    GRAPH <{graph.GRAPH_CURATION}> {{ ?lf hv:status hv:approved }}
  }}
}}""")
    label = None
    ann_ids = []
    ann_prefix = graph.annotation_iri("")
    for b in res["results"]["bindings"]:
        if "label" in b:
            label = b["label"]["value"]
        if "ann" in b:
            ann_ids.append(b["ann"]["value"][len(ann_prefix):])
    ann_ids = sorted(set(ann_ids))

    rays, annotations = [], []
    for aid in ann_ids:
        r = await _annotation_ray(aid)
        annotations.append({"annotation_id": aid, "ray": r})
        if r:
            rays.append(r)
    fix = triangulate.triangulate(rays)
    return {"poi_id": poi_id, "poi": poi, "label": label,
            "annotations": annotations, "n_rays": len(rays),
            "triangulation": fix}
