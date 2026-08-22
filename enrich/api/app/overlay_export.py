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
import struct

import numpy as np

OVERLAY_FORMAT = 1
# how far labels are baked when the fit does not say (km) — mirrors
# overlayFit.DEFAULT_MAX_VISIBILITY_KM
DEFAULT_MAX_VISIBILITY_KM = 150.0

# mirrors peakLabels.ts — kept in sync by hand, small and stable
R_EARTH_M = 6_371_000.0
DEFAULT_REFRACTION_K = 0.13
PEAK_MIN_DISTANCE_M = 500.0
PLACE_KINDS = {"city", "town", "village", "suburb", "quarter"}
PLACE_MAX_DIST_M = {"town": 80_000.0, "village": 30_000.0,
                    "suburb": 20_000.0, "quarter": 15_000.0}

# The visibility test and its evidence — every constant means one physical
# thing (measured on render 252a7ea8, docs/terrain-overlay-graduation.md
# § The label pool):
#
# * WIDE depth window  8 m + 6 %·D — "the column sees terrain at about the
#   POI's distance". 6 % is the render's own depth precision: the horizon
#   march steps 0.5 %·d and one 0.025° row moves the ground hit-point by
#   kilometres at grazing angles. Occlusion-safe: 98 % of what it rejects is
#   >2 rows below the ridge by the POI's own elevation. Class MASS.
# * TIGHT depth window 300 m + 3 %·D — "the top edge of the terrain at the
#   POI's distance is the summit itself". 300 m is the OSM-node-vs-rendered-
#   summit-edge scale (near-field residual median 220 m); 3 % the march.
# * HEIGHT band 100 m + ½ row — the POI's elevation angle from its `ele`
#   agrees with the anchor row. In METRES, not rows: the 30 m DEM renders
#   sharp cones 60–85 m low (Milešovka, Ještěd) and DSM canopy renders
#   forested tops ~25 m high; both are absolute. EVERY label must pass it —
#   measured: without it, the median "mass" label sat on terrain 139 m
#   HIGHER than the named hill, i.e. on a different landform (a 324 m hill
#   2 km in front of Malý Bezděz claiming Malý Bezděz's flank). Tight ∧
#   height ⇒ SUMMIT; wide-only ∧ height ⇒ MASS; height off ⇒ hidden.
# * AZIMUTH neighbourhood ±50 m, at least 1 and at most 3 columns — the
#   OSM node sits a column off the DEM summit or on a ridge edge (Strážný
#   vrch); own column first, nearest neighbour wins.
# * DIRECTION — a SETTLEMENT hidden everywhere in the neighbourhood, but
#   notable (priority ≥ 240 ≈ a town of 5 000) and within 100 km: "it lies
#   in that direction, behind this". Anchored at the top edge of the
#   terrain that hides it (≥ 1 km away — a column filled by a foreground
#   tree gets no direction label). Never a visibility claim. Peaks are not
#   direction material: a hidden summit is simply not in the picture.
# * Settlements are binary: the place is SEEN (tight ∧ height — the DSM
#   renders its roofs) or it is direction material; a hit at its distance
#   but a different height is the hill behind the town, not the town.
PEAK_DEPTH_REL_TOL = 0.06          # wide window, relative term
PEAK_DEPTH_ABS_M = 8.0             # wide window, absolute term (2 depth quanta)
SUMMIT_DEPTH_REL = 0.03
SUMMIT_DEPTH_ABS_M = 300.0
SUMMIT_HEIGHT_ABS_M = 100.0
AZIMUTH_WINDOW_M = 50.0
AZIMUTH_MAX_COLS = 3
DIRECTION_MIN_PRIORITY = 240.0
DIRECTION_MAX_DIST_M = 100_000.0
DIRECTION_MIN_OCCLUDER_M = 1_000.0   # not "behind" a tree in the foreground


# ---------------------------------------------------------------------------
# depth buffer wire format ("HVD1") — the AUTHORITY is enrich/terrain/
# renderer.py (encode_depth_u16 / depth_samples), mirrored here because the API
# container does not import the worker's package.
#
#   0 "HVD1" · 4 version u16 · 6 header bytes u16 · 8 width u32 · 12 height u32
#   16 depth_scale_m f32 · 20 reserved (12, zero) · 32 samples u16 LE row-major
DEPTH_BLOB_MAGIC = b"HVD1"
DEPTH_BLOB_VERSION = 1
DEPTH_BLOB_HEADER_BYTES = 32


def depth_blob_header(buf: bytes) -> dict | None:
    """{version, header_bytes, width, height, scale_m} or None when headerless."""
    if len(buf) < 16 or buf[:4] != DEPTH_BLOB_MAGIC:
        return None
    version, hlen, width, height = struct.unpack("<HHII", buf[4:16])
    scale = struct.unpack("<f", buf[16:20])[0] if hlen >= 20 and len(buf) >= 20 else None
    return {"version": version, "header_bytes": hlen, "width": width,
            "height": height, "scale_m": scale}


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
    """Depth buffer (HVD1) → (H, W) array of quanta (0 = sky)."""
    h, w = int(meta["height"]), int(meta["width"])
    head = depth_blob_header(buf)
    if head is None:
        raise ValueError("depth buffer has no HVD1 header")
    if head["version"] != DEPTH_BLOB_VERSION:
        raise ValueError(f"depth buffer version {head['version']}, "
                         f"this reader speaks {DEPTH_BLOB_VERSION}")
    hlen = head["header_bytes"]
    if hlen < 16 or hlen > len(buf):
        raise ValueError(f"depth buffer header claims {hlen} bytes")
    if (head["width"], head["height"]) != (w, h):
        raise ValueError(f"depth buffer is {head['width']}×{head['height']}, "
                         f"meta says {w}×{h}")
    q = np.frombuffer(buf[hlen:], dtype="<u2")
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


def label_priority(p: dict) -> float:
    """Unified priority: prominence for terrain features, log-population
    (mapped into prominence-like metres) for settlements — 1k ≈ 180,
    100k ≈ 360, 1M ≈ 450. Mirrors peakLabels.labelPriority."""
    if p.get("kind") in PLACE_KINDS:
        pop = p.get("population") or 0
        return max(0.0, 90 * math.log10(pop / 10)) if pop > 0 else 0.0
    return float(p.get("prominence") or 0)


def elevation_angle_deg(ele_m: float, eye_m: float, distance_m: float,
                        refraction_k: float = DEFAULT_REFRACTION_K) -> float:
    """The renderer's own formula (renderer.py): atan((h − eye)/d − d/(2R'))
    with R' = R/(1 − k)."""
    drop = distance_m * (1.0 - refraction_k) / (2.0 * R_EARTH_M)
    return math.degrees(math.atan((ele_m - eye_m) / distance_m - drop))


def _scan_column(column: np.ndarray, scale: float, D: float,
                 wide: float, tight: float):
    """Walk one column top-down. Depth is non-increasing below the skyline.
    Returns (verdict, row, depth_m):
      ("tight", r, d)  first row within the tight window (summit candidate)
      ("wide",  r, d)  no tight row, but a row within the wide window (mass)
      ("hidden", r, d) the profile passed D − wide without a hit; r/d is the
                       top edge of the terrain that hides the POI
      ("none", None, None) column is all sky
    """
    first_wide = None
    for row in range(column.shape[0]):
        qv = int(column[row])
        if qv == 0:
            continue                          # sky above the skyline
        d = qv * scale
        if abs(d - D) <= tight:
            return ("tight", row, d)
        if first_wide is None and abs(d - D) <= wide:
            first_wide = (row, d)
        if d < D - wide:
            if first_wide is not None:
                return ("wide", first_wide[0], first_wide[1])
            return ("hidden", row, d)
    if first_wide is not None:
        return ("wide", first_wide[0], first_wide[1])
    return ("none", None, None)


def project_labels(meta: dict, q: np.ndarray, peaks: list[dict],
                   cutoff_m: float | None,
                   rel_tol: float = PEAK_DEPTH_REL_TOL) -> list[dict]:
    """Label candidates with their visibility CLASS and the EVIDENCE for it.

    Per POI: bearing → column (own first, then ±1..n neighbours within
    AZIMUTH_WINDOW_M); walk the column top-down and classify (see the
    constants above):

      summit    tight depth window ∧ height band   → name + elevation
      mass      wide depth window ∧ height band    → name ("mass that belongs
                to it": a shoulder of the same massif). Height off ⇒ the
                pixel is a different landform and the POI is not shown;
                settlements are seen (tight ∧ height) or direction material
      direction a hidden SETTLEMENT, priority ≥ DIRECTION_MIN_PRIORITY,
                ≤ 100 km → dim, anchored at the top edge of what hides it

    Each label carries `seen_m` (depth at the anchor row), `dh_m` (metres by
    which the POI's own elevation angle sits above the anchor row's angle;
    None without an elevation) and `col_offset`, so a GUI can reveal exactly
    how much the label is claiming. One label per depth pixel (column, row)
    among summit+mass; direction labels sorted after all visible ones so a
    first-come layouter never lets them displace a visible label.
    """
    h, w = int(meta["height"]), int(meta["width"])
    scale = float(meta["depth_scale_m"])
    elev_max, elev_min = float(meta["elev_max_deg"]), float(meta["elev_min_deg"])
    step = (elev_max - elev_min) / h
    step_az = az_step_of(meta)
    max_distance_m = meta.get("max_distance_m")
    eye = meta.get("eye_elevation_m")
    k = float(meta.get("refraction_k", DEFAULT_REFRACTION_K))
    lat0, lon0 = float(meta["lat"]), float(meta["lon"])
    out: list[dict] = []
    for p in peaks:
        name = p.get("name")
        if not name:
            continue
        bearing, distance = bearing_distance(lat0, lon0, p["lat"], p["lon"])
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
        col0 = col_for_azimuth(meta, bearing)
        if col0 is None:
            continue
        wide = distance * rel_tol + PEAK_DEPTH_ABS_M
        tight = distance * SUMMIT_DEPTH_REL + SUMMIT_DEPTH_ABS_M
        col_w = distance * math.radians(step_az) if step_az > 0 else 1.0
        n = min(AZIMUTH_MAX_COLS, max(1, round(AZIMUTH_WINDOW_M / col_w)))
        offsets = [0] + [s * i for i in range(1, n + 1) for s in (1, -1)]
        best = None                       # (verdict, row, depth, offset)
        own = None
        for dc in offsets:
            c = col0 + dc
            if not (0 <= c < w):
                continue
            v = _scan_column(q[:, c], scale, distance, wide, tight)
            if dc == 0:
                own = v
            if v[0] == "tight":
                best = (*v, dc)
                break
            if v[0] == "wide" and best is None:
                best = (*v, dc)
        is_place = kind in PLACE_KINDS
        ele = p.get("ele")
        prio = label_priority(p)
        cls = None
        if best is not None:
            verdict, row, seen, dc = best
            row_angle = elev_max - (row + 0.5) * step
            dh = None
            if ele is not None and eye is not None:
                dtheta = elevation_angle_deg(float(ele), float(eye), distance, k) - row_angle
                dh = math.radians(dtheta) * distance
            band = SUMMIT_HEIGHT_ABS_M + 0.5 * math.radians(step) * distance
            height_ok = dh is None or abs(dh) <= band
            if verdict == "tight" and height_ok:
                cls = "summit"
            elif not is_place and height_ok:
                cls = "mass"
        if cls is None:
            # a settlement that is hidden — or whose column sees terrain near
            # it but not the place: "it lies in that direction, behind this".
            # Anchor at the top edge of what the column saw.
            if not (is_place and prio >= DIRECTION_MIN_PRIORITY
                    and distance <= DIRECTION_MAX_DIST_M):
                continue
            if best is not None:
                _, row, seen, dc = best           # place, near-miss
            elif own is not None and own[0] == "hidden":
                _, row, seen = own
                dc = 0
            else:
                continue                          # all-sky column
            if seen < DIRECTION_MIN_OCCLUDER_M:
                continue                          # foreground clutter
            row_angle = elev_max - (row + 0.5) * step
            dh, cls = None, "direction"
        out.append({
            "name": name,
            "lat": round(float(p["lat"]), 6),
            "lon": round(float(p["lon"]), 6),
            "elev_deg": round(row_angle, 4),
            "azimuth_deg": round(bearing, 3),
            "distance_m": round(distance),
            "ele": ele,
            "kind": kind,
            "prominence": p.get("prominence"),
            "population": p.get("population"),
            "class": cls,
            "seen_m": round(seen),
            "dh_m": None if dh is None else round(dh),
            "col_offset": dc,
            **({"ele_estimated": True} if p.get("ele_estimated") else {}),
            "_pix": (col0 + dc, row),
        })
    # priority order (prominence for terrain, log-population for settlements),
    # nearest first among equals — the drawing side thins by neighborhood and
    # keeps whatever comes first, so the order IS the editorial decision.
    # Direction labels go after every visible one.
    # …and among equals a confirmed SUMMIT before a mass claim (measured: two
    # foreground hills' mass claims used to outrank the real summit behind
    # them and thin it out of the layout), then nearest first.
    out.sort(key=lambda m: (m["class"] == "direction", -label_priority(m),
                            m["class"] == "mass", m["distance_m"]))
    # one label per depth pixel: if the render cannot separate two POIs, the
    # export must not pretend to. Visible classes are already ahead of
    # direction in the order, so a hidden town never keeps a pixel from a
    # visible summit.
    seen_pix: set = set()
    kept: list[dict] = []
    for m in out:
        pix = m.pop("_pix")
        if pix in seen_pix:
            continue
        seen_pix.add(pix)
        kept.append(m)
    return kept


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
    # two ranges: the DEFAULT visibility (what the viewer opens with — the
    # baked skyline is cut here so the first paint needs no depth) and the
    # MAX visibility the document is built to (labels reach it, capped by the
    # render's range) so a viewer's fog slider has room without a re-export
    vis_km = fit.get("visibility_km")
    cutoff_m = float(vis_km) * 1000.0 if vis_km is not None else None
    max_km = fit.get("max_visibility_km")
    max_m = (float(max_km) if max_km is not None else DEFAULT_MAX_VISIBILITY_KM) * 1000.0
    if cutoff_m is not None:
        max_m = max(max_m, cutoff_m)          # never bake fewer labels than the default shows
    if meta.get("max_distance_m") is not None:
        max_m = min(max_m, float(meta["max_distance_m"]))

    elev, dist = skyline_from_depth(meta, q, cutoff_m)
    labels = project_labels(meta, q, peaks, max_m)

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
        # how far the labels reach — the ceiling for a viewer's fog slider
        "labels_cutoff_km": round(max_m / 1000.0, 1),
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
