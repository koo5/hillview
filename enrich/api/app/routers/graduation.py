"""Graduation: what approved curation would push back into Hillview.

GET /api/graduation/suggestions — per-annotation body-rewrite proposals derived
from APPROVED labelText / anchorCandidate facts vs the mirrored body. Purely a
derived view: nothing here writes anywhere. The suggested body is the portable
projection of the approved facts ("Name | context | wiki | lat N, lon E"), built
to round-trip through parse_body — the export package (.trig + ops manifest) and
the Hillview-side applier are the next milestones.
"""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import facts, graph
from ..db import wb_engine
from ..parser import COORD_RE, WIKI_RE, parse_body
from ..runs import create_run, fail_run, finish_run

router = APIRouter()

PACKAGE_NAME = "hillview-enrichment"
PACKAGE_FORMAT = 1

WIKI_URL_RE = re.compile(r"^https?://\w{2,3}\.(?:m\.)?wikipedia\.org/wiki/")


def _coord_seg(lat: float, lon: float) -> str:
    return f"{lat:.5f}N, {lon:.5f}E"


def suggest_body(body: str | None, label: str | None,
                 anchor: tuple[float, float] | None,
                 wiki_url: str | None) -> tuple[str, list[dict]]:
    """→ (suggested_body, changes). Edits the body's `|`-segments in place:
    the name segment is replaced by the approved label, the coords segment by
    the approved anchor (appended if absent), a wikipedia-anchor URL appended
    when no wiki segment exists. Every other segment — context, non-wiki URLs,
    anything the parser doesn't model — is preserved verbatim, so the
    suggestion is exactly the semantic delta and untouched aspects never
    reformat."""
    p = parse_body(body)
    segs = list(p.segments) if p.segments else ["?"]
    changes: list[dict] = []

    if label and label != p.name:
        # a curated label is a certain one — uncertainty markers don't carry over
        changes.append({"what": "label", "from": segs[0] or "?", "to": label})
        segs[0] = label

    coord_idx = next((i for i, s in enumerate(segs)
                      if COORD_RE.search(s) and not WIKI_RE.search(s)), None)
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


async def _compute_suggestions() -> tuple[list[dict], list[dict]]:
    """→ (pending, landed). pending = annotations whose approved facts imply a
    body change; landed = approved facts already reflected in the body. Each item
    also carries the non-geo candidate metadata fact-graph IRIs (`meta_facts`) so
    the export can dump a self-contained provenance appendix."""
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
    if not by_ann:
        return [], []

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

    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT a.id, a.body, a.photo_id, p.sizes "
            "FROM annotation_mirror a JOIN photo_mirror p ON p.id = a.photo_id "
            "WHERE a.id = ANY(:ids) AND a.is_current AND a.missing_since IS NULL"),
            {"ids": list(by_ann)})).all()

    pending, landed = [], []
    for r in rows:
        d = by_ann[r.id]
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
        item = {"annotation_id": r.id, "photo_id": r.photo_id, "sizes": r.sizes,
                "current_body": r.body, "suggested_body": suggested,
                "changes": changes, "facts": d["facts"],
                "decided_at": d["decided_at"] or None,
                # provenance appendix: driving fact graphs + any candidate-metadata
                # fact graphs that justify the anchor's coords
                "fact_iris": [f["fact"] for f in d["facts"]]
                + (meta_facts.get(anchor_uri, []) if anchor_uri else []),
                "anchor": ({"uri": anchor_uri, "lat": anchor[0], "lon": anchor[1]}
                           if anchor else None)}
        (pending if changes else landed).append(item)
    # most recently curated first; annotation_id as a stable tiebreak
    def _key(i):
        return (i["decided_at"] or "", i["annotation_id"])
    pending.sort(key=_key, reverse=True)
    landed.sort(key=_key, reverse=True)
    return pending, landed


def _public(item: dict) -> dict:
    """Drop internal-only fields (fact_iris) from a suggestion for the GET view."""
    return {k: v for k, v in item.items() if k != "fact_iris"}


@router.get("/graduation/suggestions")
async def suggestions():
    pending, landed = await _compute_suggestions()
    return {"suggestions": [_public(i) for i in pending],
            "landed": [_public(i) for i in landed]}


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
    note: str | None = None


@router.post("/graduation/export")
async def export(req: ExportRequest):
    """Build a graduation package: a JSON ops manifest (authoritative, with body
    preconditions) + a TriG provenance appendix. Read-only w.r.t. facts — landing
    is observed via the mirror sync, so nothing is marked here; a run row records
    the export for the ledger."""
    pending, _ = await _compute_suggestions()
    if req.annotation_ids is not None:
        wanted = set(req.annotation_ids)
        pending = [i for i in pending if i["annotation_id"] in wanted]
    if not pending:
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
    # dedupe fact IRIs, preserve first-seen order
    seen: set[str] = set()
    uniq = [f for f in all_facts if not (f in seen or seen.add(f))]

    run_id = await create_run(
        kind="export",
        params={"annotation_ids": [i["annotation_id"] for i in pending]},
        note=req.note)
    try:
        trig = await _trig_appendix(uniq)
        await finish_run(run_id, stats={"ops": len(ops), "facts": len(uniq)})
        return {
            "package": PACKAGE_NAME,
            "format_version": PACKAGE_FORMAT,
            "source": f"{graph.BASE} enrichment-workbench",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run_id),
            "counts": {"ops": len(ops), "facts": len(uniq)},
            "ops": ops,
            "provenance_trig": trig,
        }
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"export failed: {e}")
