"""Geocode bench API.

POST /api/geocode/run   — background run: for current annotations' labelText facts
                          (REJECTED labels are skipped — curation feeds downstream),
                          query Nominatim (+ Wikipedia coords where a wikipediaPage
                          fact exists) and emit candidate facts.
GET  /api/annotations/{id}/candidates — candidates + metadata + live plausibility
                          (km + Δbearing vs the photo), for the map UI.
"""
import asyncio
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import calibrate, facts, geocode, graph
from ..db import wb_engine
from ..runs import create_run, fail_run, finish_run

router = APIRouter()

geocode_lock = asyncio.Lock()


def _bearing(lo1, la1, lo2, la2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dl = math.radians(lo2 - lo1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _haversine_km(lo1, la1, lo2, la2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


async def _labels_from_graph(ann_ids: list[str]) -> dict[str, dict]:
    """{ann_id: {label, wiki_url?, type_guess?, coords?: (lat,lon)}} from
    non-rejected facts."""
    if not ann_ids:
        return {}
    values = " ".join(f"<{graph.annotation_iri(a)}>" for a in ann_ids)
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?ann ?p ?o WHERE {{
  VALUES ?ann {{ {values} }}
  GRAPH ?f {{ ?ann ?p ?o }}
  FILTER(?p IN (hv:labelText, hv:wikipediaPage, hv:typeGuess, hv:embeddedCoords))
  FILTER NOT EXISTS {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status hv:rejected }} }}
}}""")
    out: dict[str, dict] = {}
    for b in res["results"]["bindings"]:
        ann_id = b["ann"]["value"].rsplit("/", 1)[-1]
        d = out.setdefault(ann_id, {})
        p, o = b["p"]["value"], b["o"]["value"]
        if p.endswith("labelText"):
            d["label"] = o
        elif p.endswith("wikipediaPage"):
            d["wiki_url"] = o
        elif p.endswith("typeGuess"):
            d["type_guess"] = o
        elif p.endswith("embeddedCoords"):
            try:
                lon, lat = o.replace("POINT(", "").rstrip(")").split()
                d["coords"] = (float(lat), float(lon))
            except ValueError:
                pass
    return out


class GeocodeRequest(BaseModel):
    scope: str = "all-current"
    photo_id: str | None = None
    annotation_ids: list[str] | None = None
    note: str | None = None


@router.post("/geocode/run")
async def geocode_run(req: GeocodeRequest):
    if geocode_lock.locked():
        raise HTTPException(409, "a geocode run is already running")

    where, params = ["a.is_current", "a.missing_since IS NULL"], {}
    if req.scope == "photo" and req.photo_id:
        where.append("a.photo_id = :pid")
        params["pid"] = req.photo_id
    elif req.scope == "annotations" and req.annotation_ids:
        where.append("a.id = ANY(:ids)")
        params["ids"] = req.annotation_ids
    async with wb_engine.connect() as conn:
        ann_ids = [r[0] for r in (await conn.execute(text(
            f"SELECT a.id FROM annotation_mirror a WHERE {' AND '.join(where)}"),
            params)).all()]

    labels = await _labels_from_graph(ann_ids)
    todo = {a: d for a, d in labels.items() if d.get("label") or d.get("coords")}
    run_id = await create_run(kind="geocode",
                              params={"scope": req.scope, "annotations": len(todo)},
                              note=req.note)

    async def _job():
        async with geocode_lock:
            try:
                import re
                triples_by_ann: dict[str, list] = {}
                stats = {"annotations": len(todo), "done": 0, "candidates": 0,
                         "wiki_hits": 0}
                stats["errors"] = 0
                for ann_id, d in todo.items():
                    try:
                        cands = (await geocode.nominatim_search(d["label"])
                                 if d.get("label") else [])
                        wiki_cand = None
                        if d.get("wiki_url"):
                            m = re.match(r"https?://(\w{2,3})\.wikipedia\.org/wiki/(.+)",
                                         d["wiki_url"])
                            if m:
                                import urllib.parse
                                wc = await geocode.wikipedia_coords(
                                    m.group(1),
                                    urllib.parse.unquote(m.group(2)).replace("_", " "))
                                if wc:
                                    wiki_cand = {"url": d["wiki_url"], **wc}
                                    stats["wiki_hits"] += 1
                        triples = facts.geocode_facts_for(
                            ann_id, cands, wiki_cand, geo_point=d.get("coords"))
                        if triples:
                            triples_by_ann[ann_id] = triples
                        stats["candidates"] += (len(cands) + (1 if wiki_cand else 0)
                                                + (1 if d.get("coords") else 0))
                    except Exception as e:
                        # one bad annotation must not kill the run
                        stats["errors"] += 1
                        print(f"geocode {ann_id}: {type(e).__name__}: {e}", flush=True)
                    stats["done"] += 1
                    if stats["done"] % 25 == 0:
                        async with wb_engine.begin() as conn:
                            await conn.execute(text(
                                "UPDATE runs SET stats = CAST(:s AS jsonb) "
                                "WHERE id = :id"),
                                {"s": __import__("json").dumps(stats),
                                 "id": run_id})

                payload = facts.build_triples_payload(triples_by_ann, run_id)
                for g_iri, nt in payload["fact_graphs"].items():
                    await graph.store.load_turtle(g_iri, nt)
                await graph.store.load_turtle(graph.GRAPH_META, payload["meta_turtle"])
                stats["facts"] = payload["n_facts"]
                await finish_run(run_id, stats=stats, graph_iri=graph.run_iri(run_id))
            except Exception as e:
                await fail_run(run_id, f"{type(e).__name__}: {e}")

    asyncio.create_task(_job())
    return {"run_id": str(run_id), "started": True, "annotations": len(todo)}


@router.get("/annotations/{ann_id}/candidates")
async def candidates(ann_id: str):
    async with wb_engine.connect() as conn:
        photo = (await conn.execute(text(
            "SELECT a.photo_id, ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat, "
            "p.compass_angle FROM annotation_mirror a "
            "JOIN photo_mirror p ON p.id = a.photo_id WHERE a.id = :id"),
            {"id": ann_id})).first()
    if not photo:
        raise HTTPException(404, "annotation not found")

    ann_iri = graph.annotation_iri(ann_id)
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?f ?cand ?status WHERE {{
  GRAPH ?f {{ <{ann_iri}> hv:anchorCandidate ?cand }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    cands = {}
    for b in res["results"]["bindings"]:
        c = {
            "candidate": b["cand"]["value"],
            "fact": b["f"]["value"],
            "status": b["status"]["value"].split("#")[-1] if "status" in b else "proposed",
        }
        # geo: candidates carry their coords in the identifier itself
        g = graph.parse_geo_uri(c["candidate"])
        if g:
            c["lat"], c["lon"] = g
        cands[b["cand"]["value"]] = c
    if cands:
        values = " ".join(f"<{c}>" for c in cands)
        meta = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?cand ?p ?o WHERE {{ VALUES ?cand {{ {values} }} GRAPH ?g {{ ?cand ?p ?o }} }}""")
        for b in meta["results"]["bindings"]:
            c = cands[b["cand"]["value"]]
            p = b["p"]["value"].split("#")[-1]
            if p == "coords":
                try:
                    lon, lat = b["o"]["value"].replace("POINT(", "").rstrip(")").split()
                    c["lon"], c["lat"] = float(lon), float(lat)
                except ValueError:
                    pass
            elif p in ("displayName", "osmType"):
                c[p] = b["o"]["value"]

    out = []
    for c in cands.values():
        if "lat" in c and photo.lat is not None:
            c["km"] = round(_haversine_km(photo.lon, photo.lat, c["lon"], c["lat"]), 2)
            if photo.compass_angle is not None:
                b = _bearing(photo.lon, photo.lat, c["lon"], c["lat"])
                c["bearing_offset"] = round(
                    (b - photo.compass_angle + 180) % 360 - 180, 1)
        out.append(c)
    out.sort(key=lambda c: c.get("km", 9e9))
    # pano view pie + this annotation's exact rect slice, so the anchor map can
    # show where the annotation LOOKS (pin anchors along the sight ray)
    from .matching import _annotation_pie, _pano_pie
    pie = await _pano_pie(photo.photo_id, photo.compass_angle,
                          slack=2.0, default_far=2000, assumed_fov=90)
    ann_pie = await _annotation_pie(ann_id, slack=2.0, default_far=2000,
                                    assumed_fov=90)
    return {"photo": {"lat": photo.lat, "lon": photo.lon,
                      "bearing": photo.compass_angle, "pie": pie},
            "annotation_pie": ann_pie,
            "candidates": out}


# ---------------------------------------------------------------------------
# Refine-anchor flow: viewpoint-aware suggestions + pin. This is the seed of
# the future user-facing entry UX (suggest-as-you-type + map pinpoint): the
# ranking uses what generic autocomplete can't — the photo's position/bearing
# (view pie), type plausibility, and on calibrated panos the predicted x of
# each candidate vs where the rect was actually drawn.
# ---------------------------------------------------------------------------

# annotation typeGuess → nominatim type substrings that corroborate it
TYPE_MATCH = {
    "tower": ("tower", "mast", "communication", "antenna", "chimney"),
    "church": ("church", "cathedral", "chapel", "place_of_worship", "monastery"),
    "hill": ("peak", "hill", "ridge", "saddle"),
    "peak": ("peak", "hill", "ridge", "saddle"),
    "castle": ("castle", "fort", "ruins", "chateau", "palace"),
    "bridge": ("bridge", "viaduct"),
    "stadium": ("stadium", "sports", "pitch"),
    "arena": ("stadium", "sports", "arena"),
}


@router.get("/annotations/{ann_id}/suggest")
async def suggest(ann_id: str, q: str | None = None):
    """Ranked Nominatim suggestions for this annotation (q defaults to its label).
    score = importance + 1·in_view + 0.5·type_match + up to 1·rect-x consistency;
    components are returned so the UI can show WHY a candidate ranks."""
    from .proto import _calibration_for
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT a.target, a.photo_id, ST_X(p.geometry) AS lon, "
            "ST_Y(p.geometry) AS lat, p.compass_angle "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = :id"), {"id": ann_id})).first()
    if not row:
        raise HTTPException(404, "annotation not found")

    parsed = await _labels_from_graph([ann_id])
    info = parsed.get(ann_id, {})
    query = (q or info.get("label") or "").strip()
    if not query:
        raise HTTPException(422, "no query and the annotation has no label")
    type_guess = info.get("type_guess")
    rx = calibrate.rect_x(row.target)
    cal = await _calibration_for(row.photo_id)

    # existing candidate statuses, to mark suggestions already in the graph
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?cand ?status WHERE {{
  GRAPH ?f {{ <{graph.annotation_iri(ann_id)}> hv:anchorCandidate ?cand }}
  OPTIONAL {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?status }} }}
}}""")
    existing = {b["cand"]["value"]:
                (b["status"]["value"].split("#")[-1] if "status" in b else "proposed")
                for b in res["results"]["bindings"]}

    hits = await geocode.nominatim_search(query)
    out = []
    for h in hits:
        s = {"candidate": geocode.osm_uri(h["osm_type"], h["osm_id"]), **h}
        s["already"] = existing.get(s["candidate"])
        score = h.get("importance") or 0.0
        if row.lat is not None:
            km = _haversine_km(row.lon, row.lat, h["lon"], h["lat"])
            s["km"] = round(km, 2)
            in_view = calibrate.MIN_KM <= km <= calibrate.kind_ceiling(h.get("type"))
            if row.compass_angle is not None:
                az = _bearing(row.lon, row.lat, h["lon"], h["lat"])
                s["bearing_offset"] = round(calibrate.ang_norm(az - row.compass_angle), 1)
                in_view = in_view and abs(s["bearing_offset"]) <= calibrate.TOL_DEG
                if cal and rx is not None:
                    x_pred = 0.5 + calibrate.ang_norm(az - cal["centre_bearing"]) / cal["fov"]
                    s["x_pred"] = round(x_pred, 3)
                    s["dx"] = round(abs(x_pred - rx), 3)
                    score += max(0.0, 1.0 - 2.0 * s["dx"])
            s["in_view"] = in_view
            score += 1.0 if in_view else 0.0
        if type_guess and any(k in (h.get("type") or "")
                              for k in TYPE_MATCH.get(type_guess, ())):
            s["type_match"] = True
            score += 0.5
        s["score"] = round(score, 3)
        out.append(s)
    out.sort(key=lambda s: -s["score"])
    return {"query": query, "type_guess": type_guess, "rect_x": rx,
            "calibrated": cal is not None,
            "photo": {"lat": row.lat, "lon": row.lon, "bearing": row.compass_angle},
            "suggestions": out}


class AnchorRequest(BaseModel):
    # exactly one of:
    point: dict | None = None        # {lat, lon} — map pinpoint → geo: URI
    candidate: dict | None = None    # nominatim-shaped suggestion to adopt
    note: str | None = None


class WikipediaRequest(BaseModel):
    url: str
    note: str | None = None


@router.post("/annotations/{ann_id}/wikipedia")
async def attach_wikipedia(ann_id: str, req: WikipediaRequest):
    """Attach a Wikipedia page as curated identity: mint + approve an
    hv:wikipediaPage fact (kind=wiki_attach run) — graduation serializes it into
    the body's wiki segment. The page title is minted as a PROPOSED labelText
    (feeds geocode queries; adopt via the label verb to make it THE name), and
    if the page has coordinates, an anchorCandidate (+coords metadata) is minted
    as PROPOSED alongside — adopt it in the Anchor section if it should become
    the anchor; an existing pin stays authoritative."""
    from datetime import datetime, timezone
    try:
        lang, raw_title, wiki_url, label = geocode.parse_wikipedia_url(req.url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    async with wb_engine.connect() as conn:
        exists = (await conn.execute(text(
            "SELECT 1 FROM annotation_mirror WHERE id = :id"), {"id": ann_id})).first()
    if not exists:
        raise HTTPException(404, "annotation not found")

    import urllib.parse as _up
    poi = await geocode.wikipedia_coords(lang, _up.unquote(raw_title))

    ann_nt = facts.iri(graph.annotation_iri(ann_id))
    triples = [(ann_nt, facts._p("wikipediaPage"), facts.iri(wiki_url)),
               (ann_nt, facts._p("labelText"), facts.lit(label))]
    if poi:
        triples += facts.geocode_facts_for(
            ann_id, [], {"url": wiki_url, "lat": poi["lat"], "lon": poi["lon"]})
    page_fact = graph.fact_iri(facts.fact_hash(*triples[0]))

    run_id = await create_run(kind="wiki_attach",
                              params={"annotation_id": ann_id, "url": wiki_url},
                              note=req.note)
    try:
        payload = facts.build_triples_payload({ann_id: triples}, run_id)
        for g_iri, nt in payload["fact_graphs"].items():
            await graph.store.load_turtle(g_iri, nt)
        await graph.store.load_turtle(graph.GRAPH_META, payload["meta_turtle"])
        await graph.store.update(facts.curate_update(
            page_fact, "approved",
            datetime.now(timezone.utc).isoformat(), note=req.note))
        await finish_run(run_id, stats={"facts": payload["n_facts"],
                                        "url": wiki_url,
                                        "coords": bool(poi)},
                         graph_iri=graph.run_iri(run_id))
        return {"run_id": str(run_id), "url": wiki_url, "label": label,
                "fact": page_fact, "coords": poi}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"wikipedia attach failed: {e}")


@router.post("/annotations/{ann_id}/anchor")
async def pin_anchor(ann_id: str, req: AnchorRequest):
    """Mint an anchorCandidate fact (geo: point or a suggested OSM object) and
    approve it — the entry-UX gesture 'THIS is what I marked', as one act."""
    from datetime import datetime, timezone
    if bool(req.point) == bool(req.candidate):
        raise HTTPException(422, "pass exactly one of point / candidate")
    async with wb_engine.connect() as conn:
        exists = (await conn.execute(text(
            "SELECT 1 FROM annotation_mirror WHERE id = :id"), {"id": ann_id})).first()
    if not exists:
        raise HTTPException(404, "annotation not found")

    if req.point:
        lat, lon = float(req.point["lat"]), float(req.point["lon"])
        triples = facts.geocode_facts_for(ann_id, [], None, geo_point=(lat, lon))
        cand_uri = graph.geo_uri(lat, lon)
    else:
        c = req.candidate
        triples = facts.geocode_facts_for(ann_id, [c], None)
        cand_uri = geocode.osm_uri(c["osm_type"], c["osm_id"])

    run_id = await create_run(kind="anchor_pin",
                              params={"annotation_id": ann_id, "candidate": cand_uri},
                              note=req.note)
    try:
        payload = facts.build_triples_payload({ann_id: triples}, run_id)
        for g_iri, nt in payload["fact_graphs"].items():
            await graph.store.load_turtle(g_iri, nt)
        await graph.store.load_turtle(graph.GRAPH_META, payload["meta_turtle"])
        # approve the anchorCandidate fact itself
        anchor_fact = graph.fact_iri(facts.fact_hash(
            facts.iri(graph.annotation_iri(ann_id)),
            facts._p("anchorCandidate"), facts.iri(cand_uri)))
        await graph.store.update(facts.curate_update(
            anchor_fact, "approved",
            datetime.now(timezone.utc).isoformat(), note=req.note))
        await finish_run(run_id, stats={"facts": payload["n_facts"],
                                        "candidate": cand_uri},
                         graph_iri=graph.run_iri(run_id))
        return {"run_id": str(run_id), "candidate": cand_uri,
                "fact": anchor_fact, "status": "approved"}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"anchor pin failed: {e}")
