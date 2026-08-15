"""Baking a terrain overlay: depth buffer + fit → the JSON document that
graduates into Hillview.

The bench draws its horizon straight from the render's uint16 depth buffer,
which is megabytes. Hillview does not need the buffer to DRAW that horizon —
it needs the curve. So the export resolves the depth once, here, and ships:

  * the skyline as an elevation angle (and distance) per azimuth sample,
  * the labels that were visible, already occlusion-tested,
  * the fit, verbatim and canonical,
  * the licence notices that ride the render.

Measured on real photo-wedge renders: ~25-50 KB raw, 6-12 KB gzipped, versus
117 KB (median) for the gzipped depth buffer alone — and no worker, artifact
store or GL context on the reading end. See docs/terrain-overlay-graduation.md.

The extraction MIRRORS shared/terrain/overlayFit.ts (skylineFromDepth) and
shared/terrain/peakLabels.ts (projectPeak) deliberately: the curator approves
what they saw on the bench, so what we bake has to be that same curve, not a
second opinion computed a slightly different way.
"""
from __future__ import annotations

import math

import numpy as np

OVERLAY_FORMAT = 1

# mirrors peakLabels.ts — kept in sync by hand, small and stable
R_EARTH_M = 6_371_000.0
PEAK_DEPTH_REL_TOL = 0.06
PEAK_MIN_DISTANCE_M = 500.0
PLACE_KINDS = {"city", "town", "village", "suburb", "quarter"}
PLACE_MAX_DIST_M = {"town": 80_000.0, "village": 30_000.0,
                    "suburb": 20_000.0, "quarter": 15_000.0}


def az_step_of(meta: dict) -> float:
    """Degrees per column. The renderer states az_step_deg explicitly; the
    span fallback has to unwrap, because a sweep that crosses north has
    az_end < az_start (e.g. 298.5° → 42.3°) and would otherwise come out
    negative — smearing the whole horizon backwards."""
    step = meta.get("az_step_deg")
    if step:
        return float(step)
    w = int(meta["width"])
    if w > 1:
        span = (float(meta["az_end"]) - float(meta["az_start"])) % 360.0
        return span / (w - 1)
    return 0.0


def azimuth_for_column(meta: dict, col: int) -> float:
    return (float(meta["az_start"]) + col * az_step_of(meta)) % 360.0


def col_for_azimuth(meta: dict, azimuth_deg: float) -> int | None:
    step = az_step_of(meta)
    if not step > 0:
        return None
    col = round(((azimuth_deg - float(meta["az_start"])) % 360.0 + 360.0) % 360.0 / step)
    return col if 0 <= col < int(meta["width"]) else None


def bearing_distance(lat1: float, lon1: float,
                     lat2: float, lon2: float) -> tuple[float, float]:
    """(bearing°, distance m) on the sphere — the same inverse geodesic the
    viewer uses, so projection and click-back agree."""
    la1, la2 = math.radians(lat1), math.radians(lat2)
    d_la = la2 - la1
    d_lo = math.radians(lon2 - lon1)
    a = (math.sin(d_la / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin(d_lo / 2) ** 2)
    distance_m = 2 * R_EARTH_M * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(d_lo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(d_lo)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0, distance_m


def decode_depth(buf: bytes, meta: dict) -> np.ndarray:
    """Raw little-endian uint16 → (H, W) array of quanta (0 = sky)."""
    h, w = int(meta["height"]), int(meta["width"])
    q = np.frombuffer(buf, dtype="<u2")
    if q.size != h * w:
        raise ValueError(f"depth buffer is {q.size} samples, meta says {h}×{w}")
    return q.reshape(h, w)


def skyline_from_depth(meta: dict, q: np.ndarray, cutoff_m: float | None
                       ) -> tuple[np.ndarray, np.ndarray]:
    """→ (elev_deg, distance_m), each (W,) float with NaN where nothing is
    visible: the topmost row per column whose terrain lies within cutoff_m.

    Below the first terrain row the column's depth is non-increasing (a lower
    ray hits terrain at or before a higher one) and the near-clip zeros sit at
    the very bottom, so "first row at-or-below the skyline satisfying q <=
    maxQ" is exactly what the bench's binary search finds — argmax over the
    boolean predicate gives the same index without assuming monotonicity.
    A near-clip zero landing first means nothing is visible: that column's
    terrain is all beyond the cutoff.
    """
    h, w = int(meta["height"]), int(meta["width"])
    scale = float(meta["depth_scale_m"])
    elev_max, elev_min = float(meta["elev_max_deg"]), float(meta["elev_min_deg"])
    step = (elev_max - elev_min) / h

    terrain = q != 0
    has_terrain = terrain.any(axis=0)
    r0 = np.argmax(terrain, axis=0)                     # topmost terrain row

    max_q = 0xFFFF if cutoff_m is None else int(cutoff_m // scale)
    rows = np.arange(h)[:, None]
    within = (q <= max_q) & (rows >= r0[None, :])
    any_within = within.any(axis=0)
    lo = np.argmax(within, axis=0)

    cols = np.arange(w)
    picked = q[lo, cols]
    ok = has_terrain & any_within & (picked != 0)

    elev = np.where(ok, elev_max - (lo + 0.5) * step, np.nan)
    dist = np.where(ok, picked.astype(np.float64) * scale, np.nan)
    return elev, dist


def project_labels(meta: dict, q: np.ndarray, peaks: list[dict],
                   cutoff_m: float | None,
                   rel_tol: float = PEAK_DEPTH_REL_TOL) -> list[dict]:
    """Label candidates that are actually VISIBLE in this render, with the
    elevation angle to anchor them at.

    Same rule as the viewer: scan the peak's column for the topmost pixel
    whose depth matches the peak's distance — the rendered summit edge. The
    column gets nearer as it descends, so once terrain is closer than the
    peak (beyond tolerance) the peak is occluded and the scan stops.
    """
    h, w = int(meta["height"]), int(meta["width"])
    scale = float(meta["depth_scale_m"])
    elev_max, elev_min = float(meta["elev_max_deg"]), float(meta["elev_min_deg"])
    step = (elev_max - elev_min) / h
    max_distance_m = meta.get("max_distance_m")
    out: list[dict] = []
    for p in peaks:
        name = p.get("name")
        if not name:
            continue
        bearing, distance = bearing_distance(
            float(meta["lat"]), float(meta["lon"]), p["lat"], p["lon"])
        if distance < PEAK_MIN_DISTANCE_M:
            continue
        if max_distance_m is not None and distance > float(max_distance_m):
            continue
        # the fit's own visibility cutoff hides what the photo's haze hid
        if cutoff_m is not None and distance > cutoff_m:
            continue
        kind = p.get("kind")
        cap = PLACE_MAX_DIST_M.get(kind) if kind else None
        if cap is not None and distance > cap:
            continue
        col = col_for_azimuth(meta, bearing)
        if col is None:
            continue
        tol = distance * rel_tol + 2 * scale
        column = q[:, col]
        for row in range(h):
            qv = int(column[row])
            if qv == 0:
                continue                      # sky above the skyline
            d = qv * scale
            if abs(d - distance) <= tol:
                out.append({
                    "name": name,
                    "lat": round(float(p["lat"]), 6),
                    "lon": round(float(p["lon"]), 6),
                    "elev_deg": round(elev_max - (row + 0.5) * step, 4),
                    "azimuth_deg": round(bearing, 3),
                    "distance_m": round(distance),
                    "ele": p.get("ele"),
                    "kind": kind,
                    "prominence": p.get("prominence"),
                    "population": p.get("population"),
                })
                break
            if d < distance - tol:
                break                         # nearer terrain: occluded
    # priority order (prominence for terrain, log-population for settlements),
    # nearest first among equals — the drawing side thins by neighborhood and
    # keeps whatever comes first, so the order IS the editorial decision
    def priority(m: dict) -> float:
        if m.get("kind") in PLACE_KINDS:
            pop = m.get("population") or 0
            return max(0.0, 90 * math.log10(pop / 10)) if pop > 0 else 0.0
        return float(m.get("prominence") or 0)

    out.sort(key=lambda m: (-priority(m), m["distance_m"]))
    return out


def _jsonable(v):
    """NaN → None; numpy scalars → python. JSON has no NaN literal and the
    document has to survive a plain json.dumps into a package file."""
    if v is None:
        return None
    f = float(v)
    return None if math.isnan(f) else f


def depth_ref(meta: dict, gz_bytes: int) -> dict:
    """The grid description that travels with the depth buffer.

    Deliberately a superset of the viewer's TerrainMeta, so the reference can
    be handed straight to pickFromDepth on the reading end — the click-back
    needs no other knowledge of how the render was made.
    """
    ref = {"width": int(meta["width"]), "height": int(meta["height"]),
           "az_start": float(meta["az_start"]), "az_end": float(meta["az_end"]),
           # ALWAYS stated, never left to the reader's span fallback: a sweep
           # crossing north has az_end < az_start (298.5° → 42.3°), and
           # (az_end - az_start)/(width-1) then comes out negative, which
           # would send every click to the wrong column
           "az_step_deg": az_step_of(meta),
           "elev_max_deg": float(meta["elev_max_deg"]),
           "elev_min_deg": float(meta["elev_min_deg"]),
           "lat": float(meta["lat"]), "lon": float(meta["lon"]),
           "depth_scale_m": float(meta["depth_scale_m"]),
           "bytes": gz_bytes}
    if meta.get("max_distance_m") is not None:
        ref["max_distance_m"] = float(meta["max_distance_m"])
    return ref


def build_overlay(*, fit: dict, meta: dict, depth: bytes, peaks: list[dict],
                  render_id: str, attribution: str,
                  label_attribution: str | None = None,
                  exported_at: str | None = None,
                  depth_gz_bytes: int | None = None,
                  elev_dp: int = 3) -> dict:
    """Bake the overlay document for one photo.

    `fit` is embedded VERBATIM: the workbench decides an overlay has landed by
    comparing exactly this sub-object against the fact it exported, so any
    rounding or key reordering here would strand the item as forever-pending.

    `depth_gz_bytes` present ⇒ the depth buffer travels with this overlay and
    the document gets a `depth` reference (its `url` is filled in on the
    hillview side, once the bytes are in a storage pool).

    An empty `attribution` is refused rather than baked. The worker's
    TERRAIN_ATTRIBUTION defaults to "" and it only writes the key when set,
    so a worker configured without it produces renders carrying no notice —
    and graduation is exactly the step that would publish those to real
    visitors, where the viewer's "show it if present" check silently shows
    nothing. Failing here keeps the licence obligation an invariant of the
    data instead of a habit (docs/terrain-data-licensing.md).
    """
    if not (attribution or "").strip():
        raise ValueError(
            "render carries no attribution — refusing to graduate terrain data "
            "without its licence notice (set TERRAIN_ATTRIBUTION on the worker "
            "and re-render)")
    q = decode_depth(depth, meta)
    vis_km = fit.get("visibility_km")
    cutoff_m = float(vis_km) * 1000.0 if vis_km is not None else None

    elev, dist = skyline_from_depth(meta, q, cutoff_m)
    labels = project_labels(meta, q, peaks, cutoff_m)

    skyline = {
        "az_start": round(azimuth_for_column(meta, 0), 6),
        "az_step": round(az_step_of(meta), 8),
        "elev_deg": [None if math.isnan(v) else round(float(v), elev_dp)
                     for v in elev],
        "distance_m": [None if math.isnan(v) else round(float(v))
                       for v in dist],
    }
    render_ref = {"id": str(render_id),
                  "lat": _jsonable(meta.get("lat")),
                  "lon": _jsonable(meta.get("lon"))}
    for k in ("eye_elevation_m", "max_distance_m", "dsm_stack"):
        if meta.get(k) is not None:
            render_ref[k] = meta[k] if k == "dsm_stack" else _jsonable(meta[k])

    doc = {
        "version": OVERLAY_FORMAT,
        "fit": fit,
        "skyline": skyline,
        "labels": labels,
        "render": render_ref,
        # licence obligation, carried BY the data: a render made from other
        # sources carries a different notice, and an old overlay keeps the
        # notice that was true when it was made
        "attribution": attribution,
    }
    if depth_gz_bytes is not None:
        # the interaction layer: with it every pixel resolves to coordinates,
        # not just the horizon line. Referenced, never inlined — the reading
        # end fetches it lazily on the first click.
        doc["depth"] = depth_ref(meta, depth_gz_bytes)
    if label_attribution and labels:
        doc["label_attribution"] = label_attribution
    if exported_at:
        doc["exported_at"] = exported_at
    return doc
