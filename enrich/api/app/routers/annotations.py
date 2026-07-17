"""GET /api/annotations (+detail) — the annotations bench data source.
Pattern: SQL page from annotation_mirror ⋈ photo_mirror first, then ONE SPARQL VALUES
query fetching the page's facts (with fact-graph IRI, curation status, runs), merged
in Python. Scale note (R6): fine at ~500-current; graph-side pagination is later debt."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import facts, graph
from ..db import wb_engine
from ..runs import create_run, fail_run, finish_run

router = APIRouter()

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
