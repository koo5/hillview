"""Photo record page: everything the workbench knows about ONE photo.

Subject-oriented counterpart to the task-oriented benches: annotations (with their
rects), facts about the photo IRI (calibration values today), match evidence in both
directions (this photo's annotations matched elsewhere / this photo as a candidate),
gold hv:depictedIn verdicts. Protos come from the existing /panos/{id}/protos.

GET /api/photos/{photo_id}
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from .. import graph, matching
from ..db import wb_engine

router = APIRouter()

MATCH_LIMIT = 50
PAGE_SIZE = 50

PANO_EXPR = ("greatest(p.width, p.height)::float / "
             "nullif(least(p.width, p.height), 0) >= 2.0")


# the photo's terrain render state, one value: a finished render with a depth
# artifact wins over anything in flight, which wins over a failure — so the
# index shows what the terrain/overlay benches can actually use
TERRAIN_EXPR = ("(SELECT tr.status FROM terrain_renders tr WHERE tr.photo_id = p.id "
                "ORDER BY (tr.status = 'done' AND tr.depth_path IS NOT NULL) DESC, "
                "(tr.status IN ('queued', 'rendering')) DESC, tr.enqueued_at DESC "
                "LIMIT 1)")


async def _overlay_states() -> dict[str, str]:
    """photo_id → 'approved' | 'saved' from hv:terrainOverlayFit facts (rejected
    ones ignored; approved = graduated/marked for export, saved = a fit exists)."""
    photo_prefix = graph.photo_iri("")
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?ph ?status WHERE {{
  GRAPH ?f {{ ?ph hv:terrainOverlayFit ?v }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    out: dict[str, str] = {}
    for b in res["results"]["bindings"]:
        ph = b["ph"]["value"]
        if not ph.startswith(photo_prefix):
            continue
        status = b.get("status", {}).get("value", "")
        if status.endswith("rejected"):
            continue
        pid = ph[len(photo_prefix):]
        if status.endswith("approved") or pid not in out:
            out[pid] = "approved" if status.endswith("approved") else "saved"
    return out


@router.get("/photos")
async def list_photos(q: str | None = None, pano: bool = False,
                      annotated: bool = False, calibrated: bool = False,
                      terrain: bool = False, overlay: bool = False,
                      page: int = 1):
    """Photo index: annotation counts + calibrated / terrain / overlay flags,
    most-annotated first. Filters: q (title/place/id-prefix), pano (aspect ≥ 2),
    annotated, calibrated, terrain (a finished render with depth), overlay (a
    saved or approved overlay fit)."""
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT DISTINCT ?ph WHERE {{ GRAPH ?f {{ ?ph hv:calibratedBearing ?o }} }}""")
    calibrated_ids = {b["ph"]["value"].rsplit("/", 1)[-1]
                      for b in res["results"]["bindings"]}
    overlays = await _overlay_states()

    where = ["p.deleted = false", "p.missing_since IS NULL"]
    params: dict = {"lim": PAGE_SIZE, "off": (max(page, 1) - 1) * PAGE_SIZE}
    if q:
        where.append("(p.title ILIKE :q OR p.place_name ILIKE :q OR p.id LIKE :qid)")
        params["q"] = f"%{q}%"
        params["qid"] = f"{q}%"
    if pano:
        where.append(PANO_EXPR)
    if calibrated:
        where.append("p.id = ANY(:cal_ids)")
        params["cal_ids"] = list(calibrated_ids) or [""]
    if terrain:
        where.append("EXISTS (SELECT 1 FROM terrain_renders tr WHERE tr.photo_id = p.id "
                     "AND tr.status = 'done' AND tr.depth_path IS NOT NULL)")
    if overlay:
        where.append("p.id = ANY(:ov_ids)")
        params["ov_ids"] = list(overlays) or [""]
    having = ("HAVING count(a.id) FILTER (WHERE a.is_current AND a.missing_since IS NULL) > 0"
              if annotated else "")
    base = (f"FROM photo_mirror p "
            f"LEFT JOIN annotation_mirror a ON a.photo_id = p.id "
            f"WHERE {' AND '.join(where)} GROUP BY p.id {having}")
    async with wb_engine.connect() as conn:
        total = (await conn.execute(text(
            f"SELECT count(*) FROM (SELECT p.id {base}) sub"), params)).scalar()
        rows = (await conn.execute(text(
            f"SELECT p.id, p.title, p.place_name, p.width, p.height, "
            f"p.compass_angle, p.sizes, p.uploaded_at, "
            f"count(a.id) FILTER (WHERE a.is_current AND a.missing_since IS NULL) AS n_annotations, "
            f"({PANO_EXPR}) AS is_pano, {TERRAIN_EXPR} AS terrain "
            f"{base} "
            f"ORDER BY n_annotations DESC, p.uploaded_at DESC NULLS LAST "
            f"LIMIT :lim OFFSET :off"), params)).all()
    return {"total": total, "page_size": PAGE_SIZE,
            "photos": [{**dict(r._mapping), "calibrated": r.id in calibrated_ids,
                        "overlay": overlays.get(r.id)}
                       for r in rows]}


def _match_row(r, overrides: dict | None = None, **extra) -> dict:
    """One match_results row for the page, plus stale_rect: whether the annotation
    has been reshaped since the matcher looked at it (a workbench reshape —
    approved proposedGeometry, `overrides` — counts as the current rect).
    params/ann_target are only carried this far to answer that, so they are
    dropped from the payload."""
    from ..geometry import apply_rect
    d = dict(r._mapping)
    target, params = d.pop("ann_target", None), d.pop("params", None)
    target = apply_rect(target, (overrides or {}).get(d.get("annotation_id")))
    d["stale_rect"] = matching.rect_is_stale(params, matching.rect_of_target(target))
    return {**d, **extra}


def _rect(target) -> dict | None:
    try:
        g = (target.get("selector") or {}).get("geometry") or {}
        r = {k: float(g[k]) for k in ("x", "y", "w", "h") if k in g}
        if "x" in r and 0 <= r["x"] <= 1:
            return r
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return None


@router.get("/photos/{photo_id}")
async def photo_detail(photo_id: str):
    async with wb_engine.connect() as conn:
        photo = (await conn.execute(text(
            "SELECT id, title, description, place_name, width, height, "
            "compass_angle, altitude, captured_at, uploaded_at, sizes, "
            "missing_since, ST_X(geometry) AS lon, ST_Y(geometry) AS lat "
            "FROM photo_mirror WHERE id = :id"), {"id": photo_id})).first()
        if not photo:
            raise HTTPException(404, "photo not found")
        anns = (await conn.execute(text(
            "SELECT id, body, target, is_current, created_at, missing_since, origin "
            "FROM annotation_mirror WHERE photo_id = :id "
            "ORDER BY is_current DESC, created_at"), {"id": photo_id})).all()
        as_pano = (await conn.execute(text(
            "SELECT m.id, m.annotation_id, m.photo_id AS candidate_id, m.status, "
            "m.raw_matches, m.inliers, m.ratio, m.error, m.overlay_path IS NOT NULL AS has_overlay, "
            "m.enqueued_at, m.params, a.target AS ann_target, "
            "a.body, c.title AS candidate_title, c.sizes AS candidate_sizes "
            "FROM match_results m "
            "JOIN annotation_mirror a ON a.id = m.annotation_id "
            "LEFT JOIN photo_mirror c ON c.id = m.photo_id "
            "WHERE a.photo_id = :id ORDER BY m.enqueued_at DESC LIMIT :lim"),
            {"id": photo_id, "lim": MATCH_LIMIT})).all()
        as_candidate = (await conn.execute(text(
            "SELECT m.id, m.annotation_id, m.status, m.raw_matches, m.inliers, "
            "m.ratio, m.error, m.overlay_path IS NOT NULL AS has_overlay, "
            "m.enqueued_at, m.params, a.target AS ann_target, "
            "a.body, a.photo_id AS pano_id, "
            "s.title AS pano_title, s.sizes AS pano_sizes "
            "FROM match_results m "
            "JOIN annotation_mirror a ON a.id = m.annotation_id "
            "LEFT JOIN photo_mirror s ON s.id = a.photo_id "
            "WHERE m.photo_id = :id ORDER BY m.enqueued_at DESC LIMIT :lim"),
            {"id": photo_id, "lim": MATCH_LIMIT})).all()

    # facts whose SUBJECT is the photo (calibration values today), FactChip-shaped
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?p ?v ?f ?status WHERE {{
  GRAPH ?f {{ <{graph.photo_iri(photo_id)}> ?p ?v }}
  FILTER STRSTARTS(STR(?f), "{graph.BASE}/id/fact/")
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    photo_facts = []
    for b in res["results"]["bindings"]:
        status = b.get("status", {}).get("value", "")
        photo_facts.append({
            "fact": b["f"]["value"],
            "predicate": b["p"]["value"].rsplit("#", 1)[-1].rsplit("/", 1)[-1],
            "value": b["v"]["value"],
            "value_type": "uri" if b["v"]["type"] == "uri" else "literal",
            "datatype": b["v"].get("datatype"),
            "status": status.rsplit("#", 1)[-1] if status else "proposed"})

    # gold verdicts where this photo is the depicted-in TARGET (object side)
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?ann ?status WHERE {{
  GRAPH ?f {{ ?ann hv:depictedIn <{graph.photo_iri(photo_id)}> }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    verdicts = {b["ann"]["value"].rsplit("/", 1)[-1]:
                (b.get("status", {}).get("value", "").rsplit("#", 1)[-1] or "proposed")
                for b in res["results"]["bindings"]}

    # approved geometry proposals (mirrored rects reshaped in the workbench) — so
    # the page can show the PROPOSED shape (pending graduation), not just the
    # mirror's still-original one
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?ann ?rect WHERE {{
  GRAPH ?f {{ ?ann hv:proposedGeometry ?rect }}
  GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status hv:approved }}
}}""")
    proposed_rects = {}
    for b in res["results"]["bindings"]:
        try:
            x, y, ww, hh = (float(v) for v in b["rect"]["value"].split(","))
            proposed_rects[b["ann"]["value"].rsplit("/", 1)[-1]] = {
                "x": x, "y": y, "w": ww, "h": hh}
        except (ValueError, KeyError):
            pass
    # the same proposals as rect tuples, for the match rows' staleness check
    # (they may reference annotations on other photos, so take them all)
    proposed_all = {a: (r["x"], r["y"], r["w"], r["h"]) for a, r in proposed_rects.items()}

    w, h = photo.width or 0, photo.height or 0
    d = dict(photo._mapping)
    d["is_pano"] = bool(w and h and max(w, h) / max(min(w, h), 1) >= 2.0)
    d["web_url"] = graph.photo_web_url(photo_id)
    # the photo's view pie for the mini-map (calibrated FOV when available;
    # same defaults as the matching bench)
    from .matching import _pano_pie
    d["pie"] = await _pano_pie(photo_id, photo.compass_angle,
                               slack=2.0, default_far=2000, assumed_fov=90)
    return {
        "photo": d,
        "annotations": [{"id": a.id, "body": a.body, "is_current": a.is_current,
                         "created_at": a.created_at, "missing": a.missing_since is not None,
                         "origin": a.origin, "rect": _rect(a.target),
                         "proposed_rect": proposed_rects.get(a.id)} for a in anns],
        "facts": photo_facts,
        "matches": {
            "as_pano": [_match_row(r, proposed_all) for r in as_pano],
            "as_candidate": [_match_row(r, proposed_all, verdict=verdicts.get(r.annotation_id, "none"))
                             for r in as_candidate]},
    }
