"""ParsedBody -> RDF facts, and the content-addressing + curation SPARQL builders.

Each fact is ONE triple (annotation subject) that lives alone in a content-addressed
named graph  fact:{sha256(canonical-ntriples)[:16]}  — so the same fact re-emitted by
any run lands on the same graph URI, and curation (keyed to that URI) survives re-runs.

Canonicalization (hash scheme "1"): N-Triples per RDF 1.1, single space separators,
`\n`-terminated, xsd datatypes made explicit. R1 in the plan: this serializer is the
single source of the hash — a change here re-mints all fact IRIs, so it is versioned
(hv:hashScheme) and isolated here.
"""
import hashlib

from . import graph
from .graph import NS, GRAPH_META, GRAPH_CURATION, LOCAL_ADMIN
from .parser import ParsedBody, PARSER_VERSION

HASH_SCHEME = "1"

XSD = "http://www.w3.org/2001/XMLSchema#"
GEO = "http://www.opengis.net/ont/geosparql#"
PROV = "http://www.w3.org/ns/prov#"


# ---------------------------------------------------------------------------
# N-Triples term encoding (canonical)
# ---------------------------------------------------------------------------

def iri(u: str) -> str:
    return f"<{u}>"


def _esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))


def lit(value: str, datatype: str | None = None) -> str:
    s = f'"{_esc(value)}"'
    return f"{s}^^<{datatype}>" if datatype else s


def _p(local: str) -> str:
    return iri(NS + local)


def _triple_nt(s: str, p: str, o: str) -> str:
    """One canonical N-Triples line (no trailing newline)."""
    return f"{s} {p} {o} ."


def fact_hash(subject: str, predicate: str, obj: str) -> str:
    nt = _triple_nt(subject, predicate, obj)
    return hashlib.sha256(nt.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# ParsedBody -> list of (predicate_nt, object_nt) for one annotation
# ---------------------------------------------------------------------------

def facts_for(parsed: ParsedBody, annotation_id: str, photo_id: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = [(_p("onPhoto"), iri(graph.photo_iri(photo_id)))]
    if parsed.name:
        out.append((_p("labelText"), lit(parsed.name)))
    if parsed.context:
        out.append((_p("context"), lit(parsed.context)))
    if parsed.wiki_url:
        out.append((_p("wikipediaPage"), iri(parsed.wiki_url)))
    if parsed.coords:
        lat, lon = parsed.coords
        out.append((_p("embeddedCoords"),
                    lit(f"POINT({lon} {lat})", f"{GEO}wktLiteral")))
    if parsed.type_guess:
        out.append((_p("typeGuess"), lit(parsed.type_guess)))
    if parsed.uncertain:
        out.append((_p("uncertain"), lit("true", f"{XSD}boolean")))
    if parsed.oops:
        out.append((_p("oopsMarker"), lit("true", f"{XSD}boolean")))
    if parsed.unnamed:
        out.append((_p("unnamed"), lit("true", f"{XSD}boolean")))
    return out


# ---------------------------------------------------------------------------
# Turtle serialization for a whole parse run (per-fact graphs + meta graph)
# ---------------------------------------------------------------------------

def run_meta_turtle(run_id, started_at_iso: str, params_json: str) -> str:
    run = graph.run_iri(run_id)
    return (
        f"{graph.PREFIXES}\n"
        f"{iri(run)} a {_p('ParseRun')} ;\n"
        f"  {iri(PROV + 'startedAtTime')} {lit(started_at_iso, XSD + 'dateTime')} ;\n"
        f"  {_p('parserVersion')} {lit(PARSER_VERSION)} ;\n"
        f"  {_p('hashScheme')} {lit(HASH_SCHEME)} ;\n"
        f"  {_p('paramsJson')} {lit(params_json)} .\n"
    )


def build_run_payload(annotations: list[dict], run_id) -> dict:
    """Return {'fact_graphs': {graph_iri: turtle}, 'meta_turtle': turtle, 'n_facts': int}.

    annotations: [{'id','photo_id','parsed': ParsedBody}]
    """
    fact_graphs: dict[str, str] = {}
    meta_lines: list[str] = []
    run = graph.run_iri(run_id)
    for a in annotations:
        subj = iri(graph.annotation_iri(a["id"]))
        for pred, obj in facts_for(a["parsed"], a["id"], a["photo_id"]):
            h = fact_hash(subj, pred, obj)
            g = graph.fact_iri(h)
            fact_graphs[g] = _triple_nt(subj, pred, obj) + "\n"
            meta_lines.append(
                f"{iri(g)} {iri(PROV + 'wasGeneratedBy')} {iri(run)} .")
            meta_lines.append(
                f"{iri(g)} {_p('about')} {iri(graph.annotation_iri(a['id']))} .")
    meta_turtle = graph.PREFIXES + "\n" + "\n".join(meta_lines) + "\n"
    return {"fact_graphs": fact_graphs, "meta_turtle": meta_turtle,
            "n_facts": len(fact_graphs)}


# ---------------------------------------------------------------------------
# geocode candidates (M2): triples for one annotation's candidates.
# The candidate object is an external identifier (OSM URI / Wikipedia page URL);
# metadata triples are about that URI, so identical metadata re-emitted for
# another annotation or run content-addresses to the SAME fact graph (dedupe).
# ---------------------------------------------------------------------------

def geocode_facts_for(annotation_id: str, candidates: list[dict],
                      wiki_candidate: dict | None,
                      geo_point: tuple[float, float] | None = None
                      ) -> list[tuple[str, str, str]]:
    """→ [(subject_nt, predicate_nt, object_nt)] for one annotation.
    candidates: nominatim dicts (lat/lon/display_name/osm_type/osm_id/type).
    wiki_candidate: {url, lat, lon} | None.
    geo_point: (lat, lon) → an anchorCandidate that IS a point (geo: URI) — from
    body-embedded coords or a map pinpoint; no metadata facts needed."""
    from .geocode import osm_uri
    ann = iri(graph.annotation_iri(annotation_id))
    out: list[tuple[str, str, str]] = []
    if geo_point:
        out.append((ann, _p("anchorCandidate"),
                    iri(graph.geo_uri(geo_point[0], geo_point[1]))))
    for c in candidates:
        cand = iri(osm_uri(c["osm_type"], c["osm_id"]))
        out.append((ann, _p("anchorCandidate"), cand))
        out.append((cand, _p("coords"),
                    lit(f"POINT({c['lon']} {c['lat']})", f"{GEO}wktLiteral")))
        if c.get("display_name"):
            out.append((cand, _p("displayName"), lit(c["display_name"])))
        if c.get("type"):
            out.append((cand, _p("osmType"), lit(c["type"])))
    if wiki_candidate:
        cand = iri(wiki_candidate["url"])
        out.append((ann, _p("anchorCandidate"), cand))
        out.append((cand, _p("coords"),
                    lit(f"POINT({wiki_candidate['lon']} {wiki_candidate['lat']})",
                        f"{GEO}wktLiteral")))
    return out


def build_triples_payload(triples_by_ann: dict[str, list[tuple[str, str, str]]],
                          run_id) -> dict:
    """Generic: {ann_id: [(s,p,o)…]} → per-fact graphs + meta turtle (fact→run,
    fact→annotation). Used by geocode (parse uses build_run_payload)."""
    fact_graphs: dict[str, str] = {}
    meta_lines: list[str] = []
    run = graph.run_iri(run_id)
    for ann_id, triples in triples_by_ann.items():
        ann = iri(graph.annotation_iri(ann_id))
        for s, p, o in triples:
            h = fact_hash(s, p, o)
            g = graph.fact_iri(h)
            fact_graphs[g] = _triple_nt(s, p, o) + "\n"
            meta_lines.append(f"{iri(g)} {iri(PROV + 'wasGeneratedBy')} {iri(run)} .")
            meta_lines.append(f"{iri(g)} {_p('about')} {ann} .")
    meta_turtle = graph.PREFIXES + "\n" + "\n".join(meta_lines) + "\n"
    return {"fact_graphs": fact_graphs, "meta_turtle": meta_turtle,
            "n_facts": len(fact_graphs)}


# ---------------------------------------------------------------------------
# curation (plain triples about the fact-graph URI, in the curation graph)
# ---------------------------------------------------------------------------

def curate_update(fact_graph_iri: str, decision: str, decided_at_iso: str,
                  curator: str = LOCAL_ADMIN, note: str | None = None) -> str:
    """SPARQL UPDATE: replace any prior decision about this fact-graph.
    decision ∈ approved | rejected | proposed (proposed = clear the decision)."""
    f = iri(fact_graph_iri)
    clear = (f"WITH {iri(GRAPH_CURATION)} DELETE {{ {f} ?p ?o }} "
             f"WHERE {{ {f} ?p ?o }}")
    if decision == "proposed":
        return f"{graph.PREFIXES}\n{clear} ;"
    status = _p(decision)  # hv:approved | hv:rejected
    ins = (f"INSERT DATA {{ GRAPH {iri(GRAPH_CURATION)} {{\n"
           f"  {f} {_p('status')} {status} ;\n"
           f"     {_p('curator')} {iri(curator)} ;\n"
           f"     {_p('decidedAt')} {lit(decided_at_iso, XSD + 'dateTime')}")
    if note:
        ins += f" ;\n     {_p('note')} {lit(note)}"
    ins += " .\n} }"
    return f"{graph.PREFIXES}\n{clear} ;\n{ins}"
