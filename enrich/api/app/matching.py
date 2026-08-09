"""View-pie candidate gating — ported from scripts/enrich/viz_app.py (case_geo/_in_pie),
knobs exposed as parameters instead of module constants.

A photo's "view pie" is the wedge (position, bearing ± half, radius = its LLM
farthest_object_distance × slack, default_far when absent). A photo is a candidate
for seeing a target point when the point is inside its pie AND the photo views it
from the same side as the pano (within ±same_side of the pano→target bearing)."""
from .calibrate import ang_norm, bearing_deg, haversine_km


def in_pie(photo: dict, target_lat: float, target_lon: float, *,
           slack: float, half: float, default_far: float) -> dict | None:
    """photo: {lat, lon, bearing, far_m}. → {dist_m, brg_to_target, off} | None."""
    if photo["lat"] is None:
        return None
    dist_km = haversine_km(photo["lon"], photo["lat"], target_lon, target_lat)
    dist_m = dist_km * 1000
    far = (photo.get("far_m") or default_far) * slack
    if dist_m > far or dist_m < 1:
        return None
    if photo.get("bearing") is None:
        return None
    brg = bearing_deg(photo["lon"], photo["lat"], target_lon, target_lat)
    off = ang_norm(brg - photo["bearing"])
    if abs(off) > half:
        return None
    return {"dist_m": round(dist_m), "brg_to_target": round(brg, 1),
            "off": round(off, 1)}


def same_side(pano_lat, pano_lon, cand_lat, cand_lon,
              target_lat, target_lon, limit: float) -> bool:
    """Candidate must view the target from within ±limit of the pano's own
    view direction to it (rejects photos of the far side of the target)."""
    b_pano = bearing_deg(pano_lon, pano_lat, target_lon, target_lat)
    b_cand = bearing_deg(cand_lon, cand_lat, target_lon, target_lat)
    return abs(ang_norm(b_cand - b_pano)) <= limit


def dest_point(lat: float, lon: float, bearing: float, meters: float) -> tuple[float, float]:
    """→ (lat, lon) of the point `meters` away along `bearing` (spherical earth).
    Used to sample points along an annotation's sight ray (ray-mode matching)."""
    import math
    R = 6371000.0
    d = meters / R
    p1, b = math.radians(lat), math.radians(bearing)
    l1 = math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0


# --- match evidence vs the rect it was computed against ------------------------
# A match_results row stores params.rect: the annotation rect the matcher actually
# saw. Reshaping the annotation afterwards (native edit, or an accepted
# proposedGeometry) leaves that evidence describing a rect that no longer exists.
# The measurement is still real, it is just no longer ABOUT the current annotation,
# so it gets flagged — never hidden, never deleted.

RECT_EPS = 1e-6   # normalized units; 1e-6 of a 176k-px pano is 0.17 px


def rect_of_target(target: dict | None) -> list[float] | None:
    """[x, y, w, h] normalized, out of an annotation's W3C target.
    None when the target carries no geometry (nothing to compare)."""
    g = ((target or {}).get("selector") or {}).get("geometry") or {}
    if not g:
        return None
    return [float(g.get("x", 0)), float(g.get("y", 0)),
            float(g.get("w", 0)), float(g.get("h", 0))]


def rect_is_stale(params: dict | None, current: list[float] | None) -> bool:
    """Did the annotation move since this result was computed? False whenever
    either side is unknown — an unanswerable question must not read as an accusation."""
    was = (params or {}).get("rect")
    if not was or not current or len(was) != 4:
        return False
    return any(abs(float(a) - float(b)) > RECT_EPS for a, b in zip(was, current))
