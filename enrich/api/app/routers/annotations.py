"""GET /api/annotations (+detail) — the annotations bench data source.
Pattern: SQL page from annotation_mirror ⋈ photo_mirror first, then ONE SPARQL VALUES
query fetching the page's facts (with fact-graph IRI, curation status, runs), merged
in Python. Scale note (R6): fine at ~500-current; graph-side pagination is later debt."""
import json
import uuid as uuid_mod

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import facts, graph
from ..db import wb_engine
from ..runs import create_run, fail_run, finish_run

router = APIRouter()


def _require_rect(target: dict) -> None:
    g = (target.get("selector") or {}).get("geometry") or {}
    if "x" not in g:
        raise HTTPException(422, "target needs a rect geometry (selector.geometry.x…)")


class NativeAnnotationCreate(BaseModel):
    photo_id: str
    body: str | None = None
    target: dict


class NativeAnnotationEdit(BaseModel):
    body: str | None = None
    target: dict | None = None


@router.post("/annotations/native")
async def create_native_annotation(req: NativeAnnotationCreate):
    """Originate a workbench-native annotation (drawn in-bench). Lives in
    annotation_mirror with origin='workbench' so POI/matching/calibration see it
    immediately; reconcile leaves it alone (no source row). Graduation to hillview
    is a later step."""
    _require_rect(req.target)
    async with wb_engine.connect() as conn:
        if not (await conn.execute(text(
                "SELECT 1 FROM photo_mirror WHERE id = :id"),
                {"id": req.photo_id})).first():
            raise HTTPException(404, "photo not found")
    ann_id = str(uuid_mod.uuid4())
    async with wb_engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO annotation_mirror (id, photo_id, body, target, is_current, "
            "event_type, origin, created_at, synced_at) VALUES "
            "(:id, :pid, :body, CAST(:target AS jsonb), true, 'created', "
            "'workbench', now(), now())"),
            {"id": ann_id, "pid": req.photo_id, "body": req.body,
             "target": json.dumps(req.target)})
    return {"id": ann_id, "photo_id": req.photo_id, "origin": "workbench"}


@router.put("/annotations/native/{ann_id}")
async def edit_native_annotation(ann_id: str, req: NativeAnnotationEdit):
    """Edit a workbench-native annotation in place (mirrored hillview rows are
    read-only here — edit those in hillview, or graduate a change)."""
    if req.target is not None:
        _require_rect(req.target)
    async with wb_engine.begin() as conn:
        row = (await conn.execute(text(
            "SELECT origin FROM annotation_mirror WHERE id = :id"),
            {"id": ann_id})).first()
        if not row:
            raise HTTPException(404, "annotation not found")
        if row.origin != "workbench":
            raise HTTPException(403, "only workbench-native annotations are editable here")
        sets, params = [], {"id": ann_id}
        if req.body is not None:
            sets.append("body = :body")
            params["body"] = req.body
        if req.target is not None:
            sets.append("target = CAST(:target AS jsonb)")
            params["target"] = json.dumps(req.target)
        if sets:
            await conn.execute(text(
                f"UPDATE annotation_mirror SET {', '.join(sets)} WHERE id = :id"), params)
    return {"id": ann_id}


@router.delete("/annotations/native/{ann_id}")
async def delete_native_annotation(ann_id: str):
    async with wb_engine.begin() as conn:
        row = (await conn.execute(text(
            "SELECT origin FROM annotation_mirror WHERE id = :id"),
            {"id": ann_id})).first()
        if not row:
            raise HTTPException(404, "annotation not found")
        if row.origin != "workbench":
            raise HTTPException(403, "only workbench-native annotations can be deleted here")
        await conn.execute(text(
            "DELETE FROM annotation_mirror WHERE id = :id"), {"id": ann_id})
    return {"deleted": ann_id}

PHOTO_FIELDS = ("p.sizes, p.width, p.height, p.compass_angle, p.title AS photo_title, "
                "p.description AS photo_description, p.place_name, "
                "ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat")


def _fact_query(ann_ids: list[str]) -> str:
    values = " ".join(f"<{graph.annotation_iri(a)}>" for a in ann_ids)
    return f"""{graph.PREFIXES}
SELECT ?ann ?f ?s ?p ?o ?status WHERE {{
  VALUES ?ann {{ {values} }}
  GRAPH <{graph.GRAPH_META}> {{ ?f hv:about ?ann }}
  GRAPH ?f {{ ?s ?p ?o }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}"""


def _short(iri_val: str) -> str:
    return iri_val.split("#")[-1].split("/")[-1]


async def _facts_by_annotation(ann_ids: list[str]) -> dict[str, list[dict]]:
    if not ann_ids:
        return {}
    res = await graph.store.query(_fact_query(ann_ids))
    out: dict[str, list[dict]] = {}
    for b in res["results"]["bindings"]:
        ann_id = b["ann"]["value"].rsplit("/", 1)[-1]
        o = b["o"]
        out.setdefault(ann_id, []).append({
            "fact": b["f"]["value"],
            # subject: the annotation IRI for parse facts, but an external URI
            # (OSM object / Wikipedia page) for geocode candidate-metadata facts
            # — the UI nests those under their anchorCandidate by matching this
            "subject": b["s"]["value"],
            "predicate": _short(b["p"]["value"]),
            "value": o["value"],
            "value_type": o["type"],                       # uri | literal
            "datatype": _short(o["datatype"]) if o.get("datatype") else None,
            "status": _short(b["status"]["value"]) if "status" in b else "proposed",
        })
    return out


@router.get("/annotations")
async def list_annotations(pano: bool = False, current: bool = True,
                           status: str | None = None, q: str | None = None,
                           photo_id: str | None = None,
                           limit: int = 50, offset: int = 0):
    where, params = ["a.missing_since IS NULL"], {}
    if current:
        where.append("a.is_current")
    if pano:
        where.append("greatest(p.width, p.height)::float / nullif(least(p.width, p.height), 0) >= 2.0")
    if q:
        where.append("a.body ILIKE :q")
        params["q"] = f"%{q}%"
    if photo_id:
        where.append("a.photo_id = :photo_id")
        params["photo_id"] = photo_id

    # status pre-filter resolves annotation IRIs graph-side first
    if status:
        if status not in ("proposed", "approved", "rejected"):
            raise HTTPException(422, "status must be proposed | approved | rejected")
        cond = (f"FILTER NOT EXISTS {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?s }} }}"
                if status == "proposed" else
                f"GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status hv:{status} }}")
        res = await graph.store.query(f"""{graph.PREFIXES}
SELECT DISTINCT ?ann WHERE {{
  GRAPH <{graph.GRAPH_META}> {{ ?f hv:about ?ann }}
  {cond}
}}""")
        ids = [b["ann"]["value"].rsplit("/", 1)[-1] for b in res["results"]["bindings"]]
        if not ids:
            return {"total": 0, "items": []}
        where.append("a.id = ANY(:status_ids)")
        params["status_ids"] = ids

    wsql = " AND ".join(where)
    async with wb_engine.connect() as conn:
        total = (await conn.execute(text(
            f"SELECT count(*) FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            f"WHERE {wsql}"), params)).scalar()
        rows = (await conn.execute(text(
            f"SELECT a.id, a.photo_id, a.body, a.is_current, a.created_at, {PHOTO_FIELDS} "
            f"FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            f"WHERE {wsql} ORDER BY a.created_at DESC NULLS LAST, a.id "
            f"LIMIT :limit OFFSET :offset"),
            {**params, "limit": min(limit, 200), "offset": offset})).all()

    facts = await _facts_by_annotation([r.id for r in rows])
    items = []
    for r in rows:
        d = dict(r._mapping)
        d["facts"] = facts.get(r.id, [])
        d["web_url"] = graph.photo_web_url(r.photo_id)
        items.append(d)
    return {"total": total, "items": items}


@router.get("/annotations/{ann_id}")
async def get_annotation(ann_id: str):
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            f"SELECT a.*, {PHOTO_FIELDS} "
            f"FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            f"WHERE a.id = :id"), {"id": ann_id})).first()
        if not row:
            raise HTTPException(404, "annotation not found")
        # supersession chain, both directions
        chain = [dict(r._mapping) for r in (await conn.execute(text(
            "WITH RECURSIVE back AS ("
            "  SELECT id, body, superseded_by, created_at, event_type, 0 AS depth "
            "  FROM annotation_mirror WHERE id = :id "
            "  UNION ALL "
            "  SELECT m.id, m.body, m.superseded_by, m.created_at, m.event_type, b.depth - 1 "
            "  FROM annotation_mirror m JOIN back b ON m.superseded_by = b.id), "
            "fwd AS ("
            "  SELECT id, body, superseded_by, created_at, event_type, 0 AS depth "
            "  FROM annotation_mirror WHERE id = :id "
            "  UNION ALL "
            "  SELECT m.id, m.body, m.superseded_by, m.created_at, m.event_type, f.depth + 1 "
            "  FROM annotation_mirror m JOIN fwd f ON f.superseded_by = m.id) "
            "SELECT DISTINCT * FROM (SELECT * FROM back UNION SELECT * FROM fwd) u "
            "ORDER BY depth"), {"id": ann_id})).all()]

    d = dict(row._mapping)
    d["facts"] = (await _facts_by_annotation([ann_id])).get(ann_id, [])
    d["web_url"] = graph.photo_web_url(row.photo_id)
    d["history"] = chain
    return d


def _rect_str(target: dict) -> str | None:
    """Annotorious target → canonical normalized 'x,y,w,h' (5 dp) or None."""
    g = (target.get("selector") or {}).get("geometry") or {}
    try:
        x, y, w, h = float(g["x"]), float(g["y"]), float(g["w"]), float(g["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= x <= 1 and 0 <= w <= 1):
        return None
    return f"{x:.5f},{y:.5f},{w:.5f},{h:.5f}"


class GeometryRequest(BaseModel):
    target: dict
    note: str | None = None


@router.post("/annotations/{ann_id}/geometry")
async def set_geometry(ann_id: str, req: GeometryRequest):
    """Propose a new rectangle for an annotation: mint + approve an
    hv:proposedGeometry fact ('x,y,w,h' normalized), demoting any prior approved
    one. For MIRRORED hillview annotations the workbench can't reshape in place
    (the mirror faithfully copies the source); this proposal graduates as a
    set_annotation_target op. (Workbench-native rects edit directly via PUT.)"""
    from datetime import datetime, timezone
    rect = _rect_str(req.target)
    if rect is None:
        raise HTTPException(422, "target needs a normalized rect geometry")
    async with wb_engine.connect() as conn:
        exists = (await conn.execute(text(
            "SELECT 1 FROM annotation_mirror WHERE id = :id"), {"id": ann_id})).first()
    if not exists:
        raise HTTPException(404, "annotation not found")

    triple = (facts.iri(graph.annotation_iri(ann_id)),
              facts._p("proposedGeometry"), facts.lit(rect))
    new_fact = graph.fact_iri(facts.fact_hash(*triple))
    now = datetime.now(timezone.utc).isoformat()

    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?f WHERE {{
  GRAPH ?f {{ <{graph.annotation_iri(ann_id)}> hv:proposedGeometry ?v }}
  GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status hv:approved }}
}}""")
    prior = [b["f"]["value"] for b in res["results"]["bindings"]
             if b["f"]["value"] != new_fact]

    run_id = await create_run(kind="geometry_edit",
                              params={"annotation_id": ann_id, "rect": rect},
                              note=req.note)
    try:
        payload = facts.build_triples_payload({ann_id: [triple]}, run_id)
        for g_iri, nt in payload["fact_graphs"].items():
            await graph.store.load_turtle(g_iri, nt)
        await graph.store.load_turtle(graph.GRAPH_META, payload["meta_turtle"])
        await graph.store.update(facts.curate_update(new_fact, "approved", now, note=req.note))
        for f in prior:
            await graph.store.update(facts.curate_update(
                f, "rejected", now, note="superseded by geometry edit"))
        await finish_run(run_id, stats={"fact": new_fact, "rect": rect,
                                        "superseded": len(prior)},
                         graph_iri=graph.run_iri(run_id))
        return {"run_id": str(run_id), "fact": new_fact, "rect": rect}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"geometry edit failed: {e}")


class LabelRequest(BaseModel):
    label: str
    note: str | None = None


@router.post("/annotations/{ann_id}/label")
async def set_label(ann_id: str, req: LabelRequest):
    """Curated rename: mint an hv:labelText fact and approve it, demoting any
    previously-approved label (superseded). The mirrored body stays untouched —
    one-way sync; pushing the name back into the Hillview annotation is the
    graduation adapter's job. Downstream (geocode) follows the approved label."""
    from datetime import datetime, timezone
    label = req.label.strip()
    if not label:
        raise HTTPException(422, "empty label")
    async with wb_engine.connect() as conn:
        exists = (await conn.execute(text(
            "SELECT 1 FROM annotation_mirror WHERE id = :id"), {"id": ann_id})).first()
    if not exists:
        raise HTTPException(404, "annotation not found")

    triple = (facts.iri(graph.annotation_iri(ann_id)),
              facts._p("labelText"), facts.lit(label))
    new_fact = graph.fact_iri(facts.fact_hash(*triple))
    now = datetime.now(timezone.utc).isoformat()

    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?f WHERE {{
  GRAPH ?f {{ <{graph.annotation_iri(ann_id)}> hv:labelText ?v }}
  GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status hv:approved }}
}}""")
    prior = [b["f"]["value"] for b in res["results"]["bindings"]
             if b["f"]["value"] != new_fact]

    run_id = await create_run(kind="label_edit",
                              params={"annotation_id": ann_id, "label": label},
                              note=req.note)
    try:
        payload = facts.build_triples_payload({ann_id: [triple]}, run_id)
        for g_iri, nt in payload["fact_graphs"].items():
            await graph.store.load_turtle(g_iri, nt)
        await graph.store.load_turtle(graph.GRAPH_META, payload["meta_turtle"])
        await graph.store.update(facts.curate_update(
            new_fact, "approved", now, note=req.note))
        for f in prior:
            await graph.store.update(facts.curate_update(
                f, "rejected", now, note=f"superseded by label edit → {label}"))
        await finish_run(run_id, stats={"fact": new_fact, "superseded": len(prior)},
                         graph_iri=graph.run_iri(run_id))
        return {"run_id": str(run_id), "fact": new_fact, "label": label,
                "superseded": prior}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"label edit failed: {e}")
