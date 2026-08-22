"""Graduation: what approved curation would push back into Hillview.

GET /api/graduation/suggestions — per-annotation body-rewrite proposals derived
from APPROVED labelText / anchorCandidate facts vs the mirrored body. Purely a
derived view: nothing here writes anywhere. The suggested body is the portable
projection of the approved facts ("Name | context | wiki | lat N, lon E"), built
to round-trip through parse_body — the export package (.trig + ops manifest) and
the Hillview-side applier are the next milestones.
"""
import base64
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import facts, graph
from ..db import wb_engine
from ..parser import parse_body
from ..runs import create_run, fail_run, finish_run

router = APIRouter()

PACKAGE_NAME = "hillview-enrichment"
PACKAGE_FORMAT = 1

# ODbL credit for the label pool; separate from the render's DEM notice so
# hiding labels in the viewer hides exactly the credit they required
OSM_ATTRIBUTION = "peaks © OpenStreetMap contributors"

WIKI_URL_RE = re.compile(r"^https?://\w{2,3}\.(?:m\.)?wikipedia\.org/wiki/")


def _coord_seg(lat: float, lon: float) -> str:
    # hemisphere letter rather than a minus sign, so the segment re-parses as
    # the same point (COORD_RE reads both, but the corpus convention is letters)
    return (f"{abs(lat):.5f}{'S' if lat < 0 else 'N'}, "
            f"{abs(lon):.5f}{'W' if lon < 0 else 'E'}")


def suggest_body(body: str | None, label: str | None,
                 anchor: tuple[float, float] | None,
                 wiki_url: str | None) -> tuple[str, list[dict]]:
    """→ (suggested_body, changes). Edits the body's `|`-segments in place:
    the name segment is replaced by the approved label, the coords segment by
    the approved anchor (appended if absent), a wikipedia-anchor URL appended
    when no wiki segment exists. Every other segment — context, non-wiki URLs,
    anything the parser doesn't model — is preserved verbatim, so the
    suggestion is exactly the semantic delta and untouched aspects never
    reformat. Segments are addressed by their PARSER role — this function never
    re-interprets the raw body itself."""
    p = parse_body(body)
    segs = list(p.segments) if p.segments else ["?"]
    roles = list(p.roles) if p.roles else ["name"]
    changes: list[dict] = []

    if label and label != p.name:
        # a curated label is a certain one — uncertainty markers don't carry over
        changes.append({"what": "label", "from": segs[0] or "?", "to": label})
        segs[0] = label
        roles[0] = "name"   # whatever occupied the slot, it now holds the name

    coord_idx = next((i for i, r in enumerate(roles) if r == "coords"), None)
    if anchor:
        same = (p.coords is not None
                and f"{p.coords[0]:.5f},{p.coords[1]:.5f}" ==
                    f"{anchor[0]:.5f},{anchor[1]:.5f}")
        if not same:
            new_seg = _coord_seg(*anchor)
            changes.append({"what": "coords",
                            "from": segs[coord_idx] if coord_idx is not None else None,
                            "to": new_seg})
            if coord_idx is not None:
                segs[coord_idx] = new_seg
            else:
                segs.append(new_seg)

    if wiki_url and not p.wiki_url:
        changes.append({"what": "wiki", "from": None, "to": wiki_url})
        segs.append(wiki_url)

    return " | ".join(segs), changes


async def _approved_context() -> tuple[dict, dict, dict]:
    """The approved-fact context shared by set-body suggestions and native
    creates: (by_ann facts map, coords_map, meta_facts)."""
    ann_prefix = graph.annotation_iri("")
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?s ?p ?v ?f ?decidedAt WHERE {{
  GRAPH ?f {{ ?s ?p ?v }}
  FILTER(?p IN (hv:labelText, hv:anchorCandidate, hv:wikipediaPage))
  GRAPH <{graph.GRAPH_CURATION}> {{
    ?f hv:status hv:approved .
    OPTIONAL {{ ?f hv:decidedAt ?decidedAt }}
  }}
}}""")
    by_ann: dict[str, dict] = {}
    for b in res["results"]["bindings"]:
        subj = b["s"]["value"]
        if not subj.startswith(ann_prefix):
            continue
        d = by_ann.setdefault(subj[len(ann_prefix):],
                              {"facts": [], "decided_at": ""})
        pred = b["p"]["value"].rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        val = b["v"]["value"]
        decided = b.get("decidedAt", {}).get("value", "")
        # most recent curation touch across the annotation's driving facts
        # (ISO-8601 UTC strings sort lexically) — for ordering the list
        d["decided_at"] = max(d["decided_at"], decided)
        d["facts"].append({"fact": b["f"]["value"], "predicate": pred,
                           "value": val, "decided_at": decided})
        if pred == "labelText":
            d["label"] = val
        elif pred == "wikipediaPage":
            d["wiki"] = val
        else:
            d.setdefault("anchors", []).append(val)

    # coords for non-geo anchor candidates live in their metadata facts; keep the
    # fact-graph IRIs too, so the provenance appendix can carry them
    non_geo = {a for d in by_ann.values() for a in d.get("anchors", [])
               if not a.startswith("geo:")}
    coords_map: dict[str, tuple[float, float]] = {}
    meta_facts: dict[str, list[str]] = {}
    if non_geo:
        values = " ".join(f"<{c}>" for c in non_geo)
        cres = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?cand ?f ?p ?w WHERE {{ VALUES ?cand {{ {values} }} GRAPH ?f {{ ?cand ?p ?w }} }}""")
        for b in cres["results"]["bindings"]:
            cand = b["cand"]["value"]
            meta_facts.setdefault(cand, []).append(b["f"]["value"])
            if b["p"]["value"].endswith("coords"):
                try:
                    lon, lat = (b["w"]["value"].replace("POINT(", "")
                                .rstrip(")").split())
                    coords_map[cand] = (float(lat), float(lon))
                except ValueError:
                    pass
    return by_ann, coords_map, meta_facts


def _build_item(r, d: dict, coords_map: dict, meta_facts: dict) -> dict:
    """One suggestion item from an annotation row `r` (id/body/photo_id/sizes/
    target) and its approved-fact bundle `d`. suggested_body + changes come from
    serializing the facts into the body; fact_iris feed the provenance appendix."""
    anchor_uri, anchor = None, None
    # approved wikipediaPage fact wins; a wiki-URL anchor also implies the page
    wiki_url = d.get("wiki")
    for a in d.get("anchors", []):
        g = graph.parse_geo_uri(a) or coords_map.get(a)
        if g:
            anchor_uri, anchor = a, g
            if not wiki_url and WIKI_URL_RE.match(a):
                wiki_url = a
            break
    suggested, changes = suggest_body(r.body, d.get("label"), anchor, wiki_url)
    return {"annotation_id": r.id, "photo_id": r.photo_id, "sizes": r.sizes,
            "current_body": r.body, "suggested_body": suggested,
            "changes": changes, "facts": d["facts"],
            "target": r.target,
            "decided_at": d.get("decided_at") or None,
            "fact_iris": [f["fact"] for f in d["facts"]]
            + (meta_facts.get(anchor_uri, []) if anchor_uri else []),
            "anchor": ({"uri": anchor_uri, "lat": anchor[0], "lon": anchor[1]}
                       if anchor else None)}


async def _compute_suggestions() -> tuple[list[dict], list[dict]]:
    """→ (pending, landed) for MIRRORED (hillview-origin) annotations. pending =
    approved facts imply a body change; landed = already reflected. Native
    (workbench-drawn) annotations are handled as create ops, not here."""
    by_ann, coords_map, meta_facts = await _approved_context()
    if not by_ann:
        return [], []
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT a.id, a.body, a.photo_id, a.target, p.sizes "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = ANY(:ids) AND a.is_current AND a.missing_since IS NULL "
            "AND a.origin = 'hillview'"),
            {"ids": list(by_ann)})).all()
    pending, landed = [], []
    for r in rows:
        item = _build_item(r, by_ann[r.id], coords_map, meta_facts)
        (pending if item["changes"] else landed).append(item)
    def _key(i):
        return (i["decided_at"] or "", i["annotation_id"])
    pending.sort(key=_key, reverse=True)
    landed.sort(key=_key, reverse=True)
    return pending, landed


async def _native_create_ops() -> list[dict]:
    """Workbench-native annotations (origin='workbench', not yet graduated) as
    create-annotation items. Body = its facts serialized (or its raw body if
    uncurated). Sorted newest-curation first, like suggestions."""
    by_ann, coords_map, meta_facts = await _approved_context()
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT a.id, a.body, a.photo_id, a.target, p.sizes "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.origin = 'workbench' AND a.is_current "
            "AND a.missing_since IS NULL"))).all()
    out = []
    for r in rows:
        d = by_ann.get(r.id, {"facts": [], "decided_at": ""})
        out.append(_build_item(r, d, coords_map, meta_facts))
    out.sort(key=lambda i: (i["decided_at"] or "", i["annotation_id"]), reverse=True)
    return out


def _rect_of(target) -> str | None:
    """A target's canonical normalized 'x,y,w,h' (5 dp), or None."""
    g = ((target or {}).get("selector") or {}).get("geometry") or {}
    try:
        return (f'{float(g["x"]):.5f},{float(g["y"]):.5f},'
                f'{float(g["w"]):.5f},{float(g["h"]):.5f}')
    except (KeyError, TypeError, ValueError):
        return None


def _rect_to_target(rect: str) -> dict:
    x, y, w, h = (float(v) for v in rect.split(","))
    return {"selector": {"type": "RECTANGLE",
                         "geometry": {"x": x, "y": y, "w": w, "h": h}}}


async def _target_ops() -> list[dict]:
    """Annotations with an approved hv:proposedGeometry fact whose rect differs
    from the mirror's CURRENT target → set-target items (a reshape to graduate).
    Already-matching ones are dropped (landed by observation after apply+sync)."""
    ann_prefix = graph.annotation_iri("")
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?s ?v ?f ?decidedAt WHERE {{
  GRAPH ?f {{ ?s hv:proposedGeometry ?v }}
  GRAPH <{graph.GRAPH_CURATION}> {{
    ?f hv:status hv:approved .
    OPTIONAL {{ ?f hv:decidedAt ?decidedAt }}
  }}
}}""")
    props = {}
    for b in res["results"]["bindings"]:
        s = b["s"]["value"]
        if not s.startswith(ann_prefix):
            continue
        props[s[len(ann_prefix):]] = {
            "rect": b["v"]["value"], "fact": b["f"]["value"],
            "decided_at": b.get("decidedAt", {}).get("value", "")}
    if not props:
        return []
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT a.id, a.body, a.photo_id, a.target, p.sizes "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = ANY(:ids) AND a.is_current AND a.missing_since IS NULL "
            # only mirrored annotations reshape via graduation; native ones edit in place
            "AND a.origin = 'hillview'"),
            {"ids": list(props)})).all()
    out = []
    for r in rows:
        pr = props[r.id]
        cur = _rect_of(r.target)
        if cur == pr["rect"]:
            continue  # already reflected
        out.append({"annotation_id": r.id, "photo_id": r.photo_id, "sizes": r.sizes,
                    "current_body": r.body, "current_rect": cur,
                    "proposed_rect": pr["rect"], "target": _rect_to_target(pr["rect"]),
                    "current_target": r.target, "decided_at": pr["decided_at"] or None,
                    "fact": pr["fact"], "fact_iris": [pr["fact"]]})
    out.sort(key=lambda i: (i["decided_at"] or "", i["annotation_id"]), reverse=True)
    return out


# ---------------------------------------------------------------------------
# terrain overlays: an approved hv:terrainOverlayFit graduates as a BAKED
# document (fit + skyline + labels + attribution) — see overlay_export.py and
# docs/terrain-overlay-graduation.md. Landing is observed the same way as
# everything else here: the mirrored photo carries the overlay back, and we
# compare its `fit` against the approved one.
# ---------------------------------------------------------------------------

async def _approved_overlay_fits() -> dict[str, dict]:
    """photo_id → {fit, fact, decided_at} for approved overlay fits. The
    graduate endpoint keeps at most one approved fit per photo; if a stale
    duplicate ever survives, the newest decision wins so the export stays
    deterministic rather than picking arbitrarily."""
    photo_prefix = graph.photo_iri("")
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?s ?v ?f ?decidedAt WHERE {{
  GRAPH ?f {{ ?s hv:terrainOverlayFit ?v }}
  GRAPH <{graph.GRAPH_CURATION}> {{
    ?f hv:status hv:approved .
    OPTIONAL {{ ?f hv:decidedAt ?decidedAt }}
  }}
}}""")
    out: dict[str, dict] = {}
    for b in res["results"]["bindings"]:
        s = b["s"]["value"]
        if not s.startswith(photo_prefix):
            continue
        pid = s[len(photo_prefix):]
        decided = b.get("decidedAt", {}).get("value", "")
        try:
            fit = json.loads(b["v"]["value"])
        except ValueError:
            continue
        prev = out.get(pid)
        if prev is None or decided > prev["decided_at"]:
            out[pid] = {"fit": fit, "fact": b["f"]["value"], "decided_at": decided}
    return out


def _canonical_fit(fit: dict | None) -> str | None:
    """The comparison key for landing. Byte-identical canonicalization on both
    sides of the trip — the exporter embeds the fit verbatim and hillview
    stores it verbatim, so this only has to agree with itself."""
    if not fit:
        return None
    return json.dumps(fit, sort_keys=True, separators=(",", ":"))


async def _overlay_ops() -> tuple[list[dict], list[dict]]:
    """→ (pending, landed) overlay items, unbaked.

    Baking an item — reading its depth artifact, resolving the skyline,
    fetching an Overpass label pool — costs real work, so it happens only in
    the export, over the narrowed selection. This view just reports what
    WOULD be exported."""
    approved = await _approved_overlay_fits()
    if not approved:
        return [], []
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT p.id, p.title, p.sizes, p.terrain_overlay "
            "FROM photo_mirror p WHERE p.id = ANY(:ids) "
            "AND p.missing_since IS NULL"),
            {"ids": list(approved)})).all()
    pending, landed = [], []
    for r in rows:
        a = approved[r.id]
        current = r.terrain_overlay or None
        if isinstance(current, str):          # jsonb arrives as text via ::text
            try:
                current = json.loads(current)
            except ValueError:
                current = None
        current_fit = _canonical_fit(current.get("fit") if current else None)
        item = {"photo_id": r.id, "photo_title": r.title, "sizes": r.sizes,
                "fit": a["fit"], "decided_at": a["decided_at"] or None,
                "fact": a["fact"], "fact_iris": [a["fact"]],
                # what hillview holds today: the apply precondition, and the
                # reason an item shows as pending rather than landed
                "current_fit": current_fit,
                "has_current": current is not None}
        if current_fit == _canonical_fit(a["fit"]):
            landed.append(item)
            continue
        pending.append(item)
    for lst in (pending, landed):
        lst.sort(key=lambda i: (i["decided_at"] or "", i["photo_id"]), reverse=True)
    return pending, landed


async def _bake_overlay(photo_id: str, fit: dict) -> tuple[dict, tuple[str, bytes] | None]:
    """Resolve the approved fit against its render.

    → (overlay document, (blob_sha256, gzipped depth bytes) | None). The depth
    buffer is what makes "click anywhere in the photo, get the coordinates"
    work on the hillview side; it rides the package as a content-addressed
    blob rather than inline, so two photos fitted against the same render
    share one copy and a re-export of an unchanged overlay is a no-op.
    """
    from .. import overlay_export
    from .terrain import _artifact_abspath, peaks as peaks_endpoint

    async with wb_engine.connect() as conn:
        # the render the fit was made against, when the run recorded one;
        # otherwise the newest finished render for this photo
        row = (await conn.execute(text("""
            SELECT tr.id, tr.meta, tr.depth_path FROM terrain_renders tr
            WHERE tr.photo_id = :pid AND tr.status = 'done'
              AND tr.depth_path IS NOT NULL AND tr.meta ? 'width'
            ORDER BY tr.id = COALESCE((
                SELECT (r.params->>'render_id')::uuid FROM runs r
                WHERE r.kind = 'overlay_fit'
                  AND r.params->>'photo_id' = :pid
                  AND r.params->'fit' = CAST(:fit AS jsonb)
                ORDER BY r.started_at DESC LIMIT 1), tr.id) DESC,
                tr.finished_at DESC
            LIMIT 1"""),
            {"pid": photo_id, "fit": json.dumps(fit)})).first()
    if not row:
        raise ValueError("no finished render with depth for this photo")
    meta = row.meta or {}
    path = _artifact_abspath(row.depth_path)
    with open(path, "rb") as f:
        depth = f.read()
    # the artifact is already the self-identifying HVD1 container the pool
    # will serve, so reuse the worker's pre-compressed sibling (uint16 depth
    # shrinks ~60:1) and fall back only if it is missing
    try:
        with open(path + ".gz", "rb") as f:
            depth_gz = f.read()
    except OSError:
        depth_gz = gzip.compress(depth, compresslevel=6)
    blob_hash = hashlib.sha256(depth_gz).hexdigest()

    # labels: the same Overpass pool the bench used, filtered to what this
    # render can actually see. A label failure degrades to no labels rather
    # than sinking the overlay — the horizon is the payload.
    peaks: list[dict] = []
    label_attribution = None
    try:
        radius = float(meta.get("max_distance_m") or 100_000.0)
        pool = await peaks_endpoint(lat=float(meta["lat"]), lon=float(meta["lon"]),
                                    radius_m=radius)
        peaks = pool.get("peaks", [])
        label_attribution = OSM_ATTRIBUTION
    except Exception as e:  # noqa: BLE001
        print(f"overlay export: peaks unavailable for {photo_id}: {e}", flush=True)

    doc = overlay_export.build_overlay(
        fit=fit, meta=meta, depth=depth, peaks=peaks,
        render_id=str(row.id),
        # the DEM licence notice the WORKER stamped into this render: an
        # overlay keeps the notice that was true when its render was made
        attribution=meta.get("attribution") or "",
        label_attribution=label_attribution,
        depth_gz_bytes=len(depth_gz),
        exported_at=datetime.now(timezone.utc).isoformat())
    doc["depth"]["blob"] = blob_hash      # resolved to a URL on apply
    return doc, (blob_hash, depth_gz)


def _public(item: dict) -> dict:
    """Drop internal-only fields (fact_iris) from a suggestion for the GET view."""
    return {k: v for k, v in item.items() if k != "fact_iris"}


@router.get("/graduation/suggestions")
async def suggestions():
    pending, landed = await _compute_suggestions()
    creates = await _native_create_ops()
    targets = await _target_ops()
    overlays, overlays_landed = await _overlay_ops()
    return {"suggestions": [_public(i) for i in pending],
            "landed": [_public(i) for i in landed],
            "creates": [_public(i) for i in creates],
            "target_changes": [_public(i) for i in targets],
            "overlays": [_public(i) for i in overlays],
            "overlays_landed": [_public(i) for i in overlays_landed]}


def _nt_term(b: dict) -> str:
    """SPARQL-JSON term → N-Triples/TriG term (no blank nodes by design)."""
    if b["type"] == "uri":
        return f"<{b['value']}>"
    if b.get("xml:lang"):
        return f'"{facts._esc(b["value"])}"@{b["xml:lang"]}'
    return facts.lit(b["value"], b.get("datatype"))


async def _trig_appendix(fact_iris: list[str]) -> str:
    """Fully-expanded TriG (no prefixes) of the cited fact graphs plus their
    meta (about / wasGeneratedBy) and curation (status / curator / decidedAt)
    subsets — the provenance appendix. Authoritative apply is the ops manifest;
    this rides along so Hillview's RDF layer can re-interpret and cross-check."""
    if not fact_iris:
        return ""
    values = " ".join(f"<{f}>" for f in fact_iris)
    out: list[str] = []

    # each fact = its own content-addressed graph, one triple
    r = await graph.store.query(
        f"SELECT ?f ?s ?p ?o WHERE {{ VALUES ?f {{ {values} }} "
        f"GRAPH ?f {{ ?s ?p ?o }} }}")
    by_g: dict[str, list[str]] = {}
    for b in r["results"]["bindings"]:
        by_g.setdefault(b["f"]["value"], []).append(
            f"{_nt_term(b['s'])} {_nt_term(b['p'])} {_nt_term(b['o'])} .")
    for g, triples in by_g.items():
        out.append(f"<{g}> {{")
        out += [f"  {t}" for t in triples]
        out.append("}")

    # meta + curation: statements ABOUT the cited fact-graph URIs
    for gname in (graph.GRAPH_META, graph.GRAPH_CURATION):
        r = await graph.store.query(
            f"SELECT ?f ?p ?o WHERE {{ VALUES ?f {{ {values} }} "
            f"GRAPH <{gname}> {{ ?f ?p ?o }} }}")
        rows = r["results"]["bindings"]
        if not rows:
            continue
        out.append(f"<{gname}> {{")
        out += [f"  <{b['f']['value']}> {_nt_term(b['p'])} {_nt_term(b['o'])} ."
                for b in rows]
        out.append("}")
    return "\n".join(out) + "\n"


class ExportRequest(BaseModel):
    # None = every pending suggestion; otherwise the chosen subset
    annotation_ids: list[str] | None = None
    # None = every pending overlay; [] = none of them
    photo_ids: list[str] | None = None
    note: str | None = None


@router.post("/graduation/export")
async def export(req: ExportRequest):
    """Build a graduation package: a JSON ops manifest (authoritative, with body
    preconditions) + a TriG provenance appendix. Read-only w.r.t. facts — landing
    is observed via the mirror sync, so nothing is marked here; a run row records
    the export for the ledger."""
    pending, _ = await _compute_suggestions()
    creates = await _native_create_ops()
    targets = await _target_ops()
    if req.annotation_ids is not None:
        wanted = set(req.annotation_ids)
        pending = [i for i in pending if i["annotation_id"] in wanted]
        creates = [i for i in creates if i["annotation_id"] in wanted]
        targets = [i for i in targets if i["annotation_id"] in wanted]
    # overlays are selected by PHOTO, not annotation — baking is the expensive
    # step, so narrow the set before doing it
    overlay_scope = None if req.photo_ids is None else set(req.photo_ids)
    overlays: list[dict] = []
    skipped: list[dict] = []
    if overlay_scope != set():
        overlays, _ = await _overlay_ops()
        if overlay_scope is not None:
            overlays = [i for i in overlays if i["photo_id"] in overlay_scope]
        for i in overlays:
            try:
                i["overlay"], i["blob"] = await _bake_overlay(i["photo_id"], i["fit"])
            except Exception as e:  # noqa: BLE001
                i["error"] = f"{type(e).__name__}: {e}"
        # a photo whose render or depth artifact has gone missing, or whose
        # render carries no licence notice, can't be baked
        skipped = [{"photo_id": i["photo_id"], "photo_title": i.get("photo_title"),
                    "error": i["error"]} for i in overlays if "overlay" not in i]
        overlays = [i for i in overlays if "overlay" in i]
        for i in skipped:
            print(f"overlay export: skipped {i['photo_id']}: {i['error']}", flush=True)
    if not pending and not creates and not targets and not overlays:
        # a bare "nothing to export" would be a lie when the work list was
        # non-empty and every item failed to bake — say which, and why
        if skipped:
            raise HTTPException(422, "no overlay could be baked: " + "; ".join(
                f"{s['photo_id'][:8]}: {s['error']}" for s in skipped))
        raise HTTPException(422, "nothing to export (no pending suggestions in scope)")

    ops, all_facts = [], []
    for i in pending:
        whats = ", ".join(c["what"] for c in i["changes"])
        ops.append({
            "op": "set_annotation_body",
            "annotation_id": i["annotation_id"],
            "photo_id": i["photo_id"],
            # precondition: apply only if Hillview's body still equals what the
            # workbench mirror last saw — a concurrent edit → skip, never clobber
            "precondition": {"body": i["current_body"]},
            "body": i["suggested_body"],
            "summary": f'{whats}: {i["current_body"] or "(empty)"} → {i["suggested_body"]}',
            "facts": [f["fact"] for f in i["facts"]],
        })
        all_facts += i["fact_iris"]
    for i in creates:
        # a workbench-drawn annotation to CREATE in hillview; annotation_id is the
        # native id, which becomes source_annotation_id there (idempotency key)
        ops.append({
            "op": "create_annotation",
            "annotation_id": i["annotation_id"],
            # provenance identity = the annotation's workbench IRI (same IRI the
            # TriG appendix uses for its facts), stored in hillview as the source
            "source_annotation_id": graph.annotation_iri(i["annotation_id"]),
            "photo_id": i["photo_id"],
            "body": i["suggested_body"],
            "target": i["target"],
            "summary": f'create: {i["suggested_body"]}',
            "facts": [f["fact"] for f in i["facts"]],
        })
        all_facts += i["fact_iris"]
    for i in targets:
        # reshape an existing (mirrored) annotation; precondition = the rect the
        # workbench last saw, so a concurrent hillview reshape → skip, never clobber
        ops.append({
            "op": "set_annotation_target",
            "annotation_id": i["annotation_id"],
            "photo_id": i["photo_id"],
            "precondition": {"rect": i["current_rect"]},
            "target": i["target"],
            "summary": f'reshape: {i["current_rect"]} → {i["proposed_rect"]}',
            "facts": [i["fact"]],
        })
        all_facts += i["fact_iris"]
    blobs: dict[str, dict] = {}
    for i in overlays:
        ov = i["overlay"]
        n_labels = len(ov.get("labels") or [])
        n_pts = sum(1 for v in ov["skyline"]["elev_deg"] if v is not None)
        if i.get("blob"):
            h, data = i["blob"]
            # content-addressed: photos sharing a render share one copy
            blobs.setdefault(h, {"encoding": "gzip+base64", "bytes": len(data),
                                 "data": base64.b64encode(data).decode("ascii")})
        ops.append({
            "op": "set_terrain_overlay",
            "photo_id": i["photo_id"],
            # precondition: the fit hillview currently holds (None = no overlay
            # yet). A concurrent overlay from elsewhere → skip, never clobber
            "precondition": {"fit": i["current_fit"]},
            "overlay": ov,
            "summary": (f'terrain overlay: horizon {n_pts} pts, {n_labels} labels'
                        f' ({ov["fit"]["projection"]}, fov {ov["fit"]["fov_deg"]}°)'),
            "facts": [i["fact"]],
        })
        all_facts += i["fact_iris"]
    # dedupe fact IRIs, preserve first-seen order
    seen: set[str] = set()
    uniq = [f for f in all_facts if not (f in seen or seen.add(f))]

    run_id = await create_run(
        kind="export",
        params={"annotation_ids": [i["annotation_id"] for i in pending],
                "photo_ids": [i["photo_id"] for i in overlays]},
        note=req.note)
    try:
        trig = await _trig_appendix(uniq)
        blob_bytes = sum(b["bytes"] for b in blobs.values())
        await finish_run(run_id, stats={"ops": len(ops), "facts": len(uniq),
                                        "blobs": len(blobs),
                                        "blob_bytes": blob_bytes})
        pkg = {
            "package": PACKAGE_NAME,
            "format_version": PACKAGE_FORMAT,
            "source": f"{graph.BASE} enrichment-workbench",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run_id),
            "counts": {"ops": len(ops), "facts": len(uniq),
                       "blobs": len(blobs), "blob_bytes": blob_bytes},
            "ops": ops,
            "provenance_trig": trig,
        }
        if blobs:
            # binary side-carriage, keyed by sha256 of the stored bytes. Kept
            # out of the ops so the manifest stays readable (and diffable) —
            # an op references its blob by hash, the applier files the bytes
            # into a storage pool and rewrites the reference to a URL.
            pkg["blobs"] = blobs
        if skipped:
            # the package is SHORT of what the review page offered; saying so
            # here is the only way the operator finds out
            pkg["skipped"] = skipped
        return pkg
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"export failed: {e}")
