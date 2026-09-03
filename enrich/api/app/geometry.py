"""The effective rect of an annotation = its approved hv:proposedGeometry (a
reshape made in the workbench, pending graduation) over the mirrored target.

The mirror is faithful to Hillview by design, so a workbench reshape lives in
the graph as a curated proposal. Until it graduates and syncs back, every
consumer of a rect — calibration, matching, POI rays, transfer, staleness —
must read through here, or the bench keeps measuring the old rect while the
photo page shows the new one ("one state": docs/one-state.md)."""
import copy

from . import graph


async def proposed_rects(ann_ids: list[str] | None = None) -> dict[str, tuple[float, float, float, float]]:
    """annotation_id → (x, y, w, h) of its APPROVED proposedGeometry fact.
    None = every annotation that has one (a small set)."""
    values = (f"VALUES ?ann {{ {' '.join(f'<{graph.annotation_iri(a)}>' for a in ann_ids)} }}"
              if ann_ids else "")
    if ann_ids is not None and not ann_ids:
        return {}
    res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?ann ?rect WHERE {{
  {values}
  GRAPH ?f {{ ?ann hv:proposedGeometry ?rect }}
  GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status hv:approved }}
}}""")
    out = {}
    for b in res["results"]["bindings"]:
        try:
            x, y, w, h = (float(v) for v in b["rect"]["value"].split(","))
        except (ValueError, KeyError):
            continue
        out[b["ann"]["value"].rsplit("/", 1)[-1]] = (x, y, w, h)
    return out


def apply_rect(target, rect: tuple[float, float, float, float] | None):
    """A copy of the (Annotorious) target with its rectangle geometry replaced
    by `rect`; the target itself when there is nothing to apply."""
    if not rect or not isinstance(target, dict):
        return target
    t = copy.deepcopy(target)
    sel = t.get("selector")
    sels = sel if isinstance(sel, list) else [sel]
    for s in sels:
        if isinstance(s, dict) and isinstance(s.get("geometry"), dict):
            g = s["geometry"]
            g["x"], g["y"], g["w"], g["h"] = rect
            g.pop("bounds", None)   # pixel bounds of the old rect would now lie
    return t


async def effective_target(ann_id: str, target):
    """One annotation's rect as the workbench currently means it."""
    return apply_rect(target, (await proposed_rects([ann_id])).get(ann_id))


async def effective_targets(rows, id_attr: str = "id", target_attr: str = "target") -> dict:
    """{annotation_id: effective target} for a batch of DB rows."""
    ids = [getattr(r, id_attr) for r in rows]
    over = await proposed_rects(ids)
    return {getattr(r, id_attr): apply_rect(getattr(r, target_attr), over.get(getattr(r, id_attr)))
            for r in rows}
