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
