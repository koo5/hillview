"""Enrichment graduation packages: read what the enrichment workbench exported
(a JSON ops manifest + a TriG provenance appendix) so the admin UI can review
and apply approved annotation-body edits.

The ops manifest is AUTHORITATIVE for applying. The TriG appendix is parsed
(pyoxigraph, best-effort) only to surface provenance — which fact, curated by
whom, when — in the review UI. This module is where RDF first enters the
Hillview API: a read/validate concern, not a triplestore.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from common.config import get_graduation_applied_dir, get_graduation_incoming_dir

logger = logging.getLogger(__name__)

PACKAGE_MARKER = "hillview-enrichment"
FACT_PREFIX = "https://rdf.hillview.cz/id/fact/"
CURATION_GRAPH = "https://rdf.hillview.cz/id/graph/curation"


def _safe_path(base: Path, filename: str) -> Path:
    """Resolve base/filename, refusing anything that escapes base (traversal)."""
    p = (base / filename).resolve()
    if p.parent != base.resolve():
        raise FileNotFoundError(filename)
    return p


def list_packages() -> list[dict]:
    """Header info for every package file in the incoming dir (no per-op work)."""
    d = get_graduation_incoming_dir()
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            pkg = json.loads(f.read_text())
            out.append({
                "filename": f.name,
                "package": pkg.get("package"),
                "format_version": pkg.get("format_version"),
                "source": pkg.get("source"),
                "created_at": pkg.get("created_at"),
                "counts": pkg.get("counts"),
                "n_ops": len(pkg.get("ops", [])),
                "valid": pkg.get("package") == PACKAGE_MARKER,
            })
        except (json.JSONDecodeError, OSError) as e:
            out.append({"filename": f.name, "valid": False, "error": str(e)[:200]})
    return out


def read_package(filename: str) -> dict:
    f = _safe_path(get_graduation_incoming_dir(), filename)
    if not f.is_file():
        raise FileNotFoundError(filename)
    pkg = json.loads(f.read_text())
    if pkg.get("package") != PACKAGE_MARKER:
        raise ValueError("not a hillview-enrichment package")
    return pkg


def _short(iri: str) -> str:
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def parse_provenance(trig: Optional[str]) -> dict[str, dict]:
    """fact IRI → {predicate, object, status, decided_at, curator}. Best-effort:
    returns {} if pyoxigraph is unavailable or the TriG does not parse, so the
    applier never depends on the RDF layer being present."""
    if not trig:
        return {}
    try:
        from pyoxigraph import Store
        store = Store()
        try:
            from pyoxigraph import RdfFormat
            store.load(trig.encode(), format=RdfFormat.TRIG)
        except (ImportError, TypeError):
            store.load(trig.encode(), mime_type="application/trig")
    except Exception as e:  # missing dep, parse error — degrade gracefully
        logger.warning("graduation: provenance TriG unavailable: %s", e)
        return {}

    prov: dict[str, dict] = {}
    for q in store.quads_for_pattern(None, None, None, None):
        g = getattr(q.graph_name, "value", None)
        p = q.predicate.value
        oval = getattr(q.object, "value", str(q.object))
        if g and g.startswith(FACT_PREFIX):
            # the fact's own triple lives in the graph named by its fact IRI
            d = prov.setdefault(g, {})
            d["predicate"], d["object"] = _short(p), oval
        elif g == CURATION_GRAPH:
            # statements about the fact-graph URI (subject == the fact IRI)
            d = prov.setdefault(q.subject.value, {})
            key = _short(p)
            if key == "status":
                d["status"] = _short(oval)
            elif key == "decidedAt":
                d["decided_at"] = oval
            elif key == "curator":
                d["curator"] = _short(oval)
    return prov


def photo_osd(photo) -> dict:
    """Photo row → the OSD source fields the review viewer needs (mirrors the
    enrich photo page's pyramid/url/dims selection)."""
    sizes = photo.sizes or {}
    full = sizes.get("full") or {}
    pyr = full.get("pyramid")

    def _u(*keys):
        for k in keys:
            u = (sizes.get(k) or {}).get("url")
            if u:
                return u
        return None

    return {
        "photo_id": photo.id,
        "url": full.get("url") or _u("1024", "640"),
        "fallback_url": _u("1024", "640", "320"),
        "pyramid": pyr if (pyr or {}).get("type") == "dzi" else None,
        "width": (pyr or {}).get("width") or photo.width or full.get("width"),
        "height": (pyr or {}).get("height") or photo.height or full.get("height"),
    }


def rect_of(target) -> str | None:
    """A target's canonical normalized 'x,y,w,h' (5 dp) — the comparison key for
    set_annotation_target ops (raw target JSON is float/key-order fragile)."""
    g = ((target or {}).get("selector") or {}).get("geometry") or {}
    try:
        return (f'{float(g["x"]):.5f},{float(g["y"]):.5f},'
                f'{float(g["w"]):.5f},{float(g["h"]):.5f}')
    except (KeyError, TypeError, ValueError):
        return None


def classify(precondition_body, current_body, suggested_body, found: bool) -> str:
    """clean = current still matches what the workbench saw; conflict = it
    changed since; already_applied = current already equals the suggestion;
    missing = the annotation is gone."""
    if not found:
        return "missing"
    if current_body == suggested_body:
        return "already_applied"
    if precondition_body == current_body:
        return "clean"
    return "conflict"


def move_to_applied(filename: str) -> None:
    """Filesystem ledger: a fully-applied package leaves the incoming dir."""
    src = _safe_path(get_graduation_incoming_dir(), filename)
    dst_dir = get_graduation_applied_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    src.rename(dst_dir / filename)
