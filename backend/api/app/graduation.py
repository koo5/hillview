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
import os
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
    """Header info for every package file in the incoming dir (no per-op work).

    Cost note: this parses each file whole, which was free when packages were
    annotation manifests but is not once they carry terrain-overlay depth
    blobs (~170 KB of base64 per distinct render). Ten un-archived packages of
    twenty overlays each is ~30 MB of JSON parsed on the event loop per admin
    page load. Bounded in practice — packages leave the incoming dir once
    fully applied, and overlays are curated a handful at a time — but if that
    stops being true, the fix is to store blobs as sidecar files next to the
    manifest rather than to parse more cleverly."""
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


def canonical_fit(fit) -> str | None:
    """An overlay fit's canonical JSON — the comparison key for
    set_terrain_overlay ops, the way rect_of is for target ops (raw dict
    comparison is key-order and float-formatting fragile).

    Only the FIT is ever compared, never the whole overlay document: the baked
    skyline is a function of whichever render was current, and hillview-side
    fine-tuning lives in `user_adjust`, so a broader comparison would make
    settled overlays look permanently out of date to the workbench."""
    if not fit:
        return None
    try:
        return json.dumps(fit, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def _depth_identity(depth) -> str | None:
    """The content hash a depth reference points at, from either side of the
    trip: a package op names it as `blob`, a stored document as the sha256 in
    its pool URL (terrain/<sha256>.depth.bin.gz)."""
    if not depth:
        return None
    if depth.get("blob"):
        return depth["blob"]
    url = depth.get("url") or ""
    name = url.rsplit("/", 1)[-1]
    return name.split(".", 1)[0] or None


def _comparable_overlay(overlay) -> dict:
    """An overlay reduced to what is meaningfully the same across the trip:
    `user_adjust` dropped (hillview's own, never travels in a package) and the
    depth reference reduced to its content hash (`blob` before apply, a pool
    URL after)."""
    out = {k: v for k, v in overlay.items() if k not in ("user_adjust", "depth")}
    if overlay.get("depth"):
        d = {k: v for k, v in overlay["depth"].items() if k not in ("blob", "url")}
        d["_id"] = _depth_identity(overlay["depth"])
        out["depth"] = d
    return out


def overlay_payload_equal(stored, proposed) -> bool:
    """Is the stored overlay already what this op proposes?

    A different question from the fit comparison: the fit decides whether the
    WORKBENCH considers an overlay landed, but a re-render from a better
    elevation model keeps the alignment while changing the skyline, the labels
    and the depth blob. Treating that as "already applied" would make an
    improved overlay impossible to publish without perturbing the fit."""
    if not stored or not proposed:
        return False
    return _comparable_overlay(stored) == _comparable_overlay(proposed)


def classify_overlay(precondition_fit, current_fit, proposed_fit, found: bool,
                     payload_equal: bool = False) -> str:
    """clean / conflict / already_applied / missing for a terrain overlay op.
    The fit arguments are canonical fit strings (or None = no overlay).

    `already_applied` means the stored document IS the proposed one — not
    merely that the alignments agree, so a re-rendered overlay still offers
    itself. `conflict` remains a question about the FIT: it asks whether
    hillview's alignment moved since the workbench last looked."""
    if not found:
        return "missing"
    if payload_equal:
        return "already_applied"
    if precondition_fit == current_fit:
        return "clean"
    return "conflict"


def overlay_stats(overlay: Optional[dict]) -> dict:
    """Reviewable shape of an overlay document — what the admin UI shows
    instead of tens of KB of coordinates."""
    if not overlay:
        return {}
    sky = overlay.get("skyline") or {}
    elev = sky.get("elev_deg") or []
    fit = overlay.get("fit") or {}
    return {
        "points": sum(1 for v in elev if v is not None),
        "samples": len(elev),
        "labels": len(overlay.get("labels") or []),
        "projection": fit.get("projection"),
        "fov_deg": fit.get("fov_deg"),
        "centre_bearing": fit.get("centre_bearing"),
        "visibility_km": fit.get("visibility_km"),
        "render_id": (overlay.get("render") or {}).get("id"),
        # the click-anywhere layer: whether it came along, and how much the
        # reviewer is about to file into the storage pool
        "depth_bytes": (overlay.get("depth") or {}).get("bytes"),
        "depth_grid": (f'{overlay["depth"]["width"]}×{overlay["depth"]["height"]}'
                       if overlay.get("depth") else None),
        # a licence obligation travels with the data — the reviewer sees the
        # notice they are about to start publishing
        "attribution": overlay.get("attribution"),
        "label_attribution": overlay.get("label_attribution"),
    }


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


TERRAIN_BLOB_DIR = "terrain"


def store_depth_blob(pkg: dict, blob_hash: str) -> str:
    """File a package blob (the overlay's gzipped depth buffer) into the write
    pool and return its public URL.

    Content-addressed by the sha256 the package declares, VERIFIED here — the
    name is the identity, so writing bytes that hash to something else would
    poison every overlay pointing at that name. Re-applying the same package,
    or two photos fitted against one render, resolve to the same file and the
    write is skipped.

    The bytes are stored gzip-compressed as-is; the pool's web server serves
    them with Content-Encoding: gzip (the .gz suffix is what tells it so),
    exactly like the workbench's own depth artifacts.
    """
    import base64
    import hashlib

    blob = (pkg.get("blobs") or {}).get(blob_hash)
    if not blob:
        raise KeyError(f"package has no blob {blob_hash}")
    data = base64.b64decode(blob["data"])
    actual = hashlib.sha256(data).hexdigest()
    if actual != blob_hash:
        raise ValueError(f"blob hash mismatch: declared {blob_hash}, got {actual}")

    from common.config import get_write_pool
    pool = get_write_pool()
    rel = f"{TERRAIN_BLOB_DIR}/{blob_hash}.depth.bin.gz"
    path = Path(pool["path"]) / rel
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # temp + rename: a reader may already be fetching this name (another
        # photo sharing the render), and a half-written depth buffer decodes
        # to garbage rather than failing loudly
        tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
        tmp.write_bytes(data)
        tmp.rename(path)
        logger.info("graduation: stored depth blob %s (%d bytes)", rel, len(data))
    return pool["url"].rstrip("/") + "/" + rel


def resolve_overlay_blobs(pkg: dict, overlay: dict) -> dict:
    """Return `overlay` with its depth reference pointing at a stored URL
    instead of a package blob. Overlays without depth pass through."""
    depth = (overlay or {}).get("depth")
    blob_hash = (depth or {}).get("blob")
    if not blob_hash:
        return overlay
    url = store_depth_blob(pkg, blob_hash)
    resolved = {k: v for k, v in depth.items() if k != "blob"}
    resolved["url"] = url
    return {**overlay, "depth": resolved}


def move_to_applied(filename: str) -> None:
    """Filesystem ledger: a fully-applied package leaves the incoming dir."""
    src = _safe_path(get_graduation_incoming_dir(), filename)
    dst_dir = get_graduation_applied_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    src.rename(dst_dir / filename)
