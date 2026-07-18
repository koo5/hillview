"""Pano calibration: Theil-Sen fit of anchor-azimuth vs rectangle-x, per pano.
Ported from scripts/enrich/calibrate_panos.py / resolve_anchors.py.

Model (equirect assumption, same caveat as the original: rectilinear panos would
need their .pto projection): delta(x) = a + b·x, where
  x     = annotation rect centre (normalized 0..1 across the pano)
  delta = ang_norm(azimuth(photo→anchor) − stored compass_angle)
Then FOV = |b| (degrees across the full width), centre bearing = compass + a + b/2,
bias-at-centre = a + b/2. Residuals identify wrong anchors (or wrong rects).
"""
import math

TOL_DEG = 90.0     # candidate auto-pick: bearing half-window vs stored compass
PEAK_KM = 150.0    # natural features are legitimately far
NEAR_KM = 40.0     # buildings/places should be near-ish
MIN_KM = 0.2       # closer than this = "at camera", useless for azimuth


def ang_norm(d: float) -> float:
    return (d + 180.0) % 360.0 - 180.0


def rect_x(target) -> float | None:
    """Annotation rect centre x (normalized 0..1) from the target JSON, or None."""
    try:
        g = (target.get("selector") or {}).get("geometry") or {}
        x, w = float(g["x"]), float(g.get("w", 0))
        if 0 <= x <= 1 and 0 < w <= 1:
            return x + w / 2
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return None


def bearing_deg(lo1, la1, lo2, la2) -> float:
    p1, p2 = math.radians(la1), math.radians(la2)
    dl = math.radians(lo2 - lo1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def haversine_km(lo1, la1, lo2, la2) -> float:
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def kind_ceiling(osm_type: str | None) -> float:
    t = osm_type or ""
    return PEAK_KM if any(k in t for k in
                          ("peak", "hill", "volcano", "ridge", "massif", "natural")) else NEAR_KM


def theil_sen(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """→ (intercept a, slope b) for y = a + b·x, robust to outliers. None if <2 pts."""
    n = len(xs)
    if n < 2:
        return None
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i])
              for i in range(n) for j in range(i + 1, n) if xs[j] != xs[i]]
    if not slopes:
        return None
    slopes.sort()
    b = slopes[len(slopes) // 2]
    residuals = sorted(y - b * x for x, y in zip(xs, ys))
    a = residuals[len(residuals) // 2]
    return a, b


def fit_summary(points: list[dict], compass: float | None) -> dict | None:
    """points: [{x, delta}] (delta vs compass). → fit params + per-point residuals."""
    if len(points) < 2:
        return None
    fit = theil_sen([p["x"] for p in points], [p["delta"] for p in points])
    if not fit:
        return None
    a, b = fit
    for p in points:
        p["residual"] = round(p["delta"] - (a + b * p["x"]), 2)
    rms = math.sqrt(sum(p["residual"] ** 2 for p in points) / len(points))
    centre_bias = a + b * 0.5
    return {
        "intercept": round(a, 2), "slope": round(b, 2),
        "fov": round(abs(b), 1),
        "centre_bias": round(centre_bias, 2),
        "centre_bearing": (round((compass + centre_bias) % 360, 2)
                           if compass is not None else None),
        "rms": round(rms, 2),
        "n": len(points),
    }


def pick_anchor(candidates: list[dict], photo_lon, photo_lat, compass,
                importance: dict[str, float]) -> tuple[dict | None, str]:
    """Choose one anchor per annotation. approved > wikipedia > best in-view nominatim
    (by cached importance, fallback nearest). → (candidate|None, rule)."""
    located = [c for c in candidates if c.get("lat") is not None]
    if not located:
        return None, "none"
    approved = [c for c in located if c["status"] == "approved"]
    if approved:
        return approved[0], "approved"
    nonrejected = [c for c in located if c["status"] != "rejected"]
    if not nonrejected:
        return None, "all-rejected"
    # geo: candidates = author/curator-given points (body-embedded coords or map
    # pins); strongest un-curated signal, above external lookups
    pinned = [c for c in nonrejected if c["candidate"].startswith("geo:")]
    if pinned:
        return pinned[0], "pinned"
    wiki = [c for c in nonrejected if "wikipedia.org" in c["candidate"]]
    if wiki:
        return wiki[0], "wikipedia"
    def in_view(c):
        km = haversine_km(photo_lon, photo_lat, c["lon"], c["lat"])
        if not (MIN_KM <= km <= kind_ceiling(c.get("osmType"))):
            return False
        if compass is not None:
            db = ang_norm(bearing_deg(photo_lon, photo_lat, c["lon"], c["lat"]) - compass)
            if abs(db) > TOL_DEG:
                return False
        return True
    pool = [c for c in nonrejected if in_view(c)] or []
    if not pool:
        return None, "no-in-view"
    best = max(pool, key=lambda c: importance.get(c["candidate"], 0.0))
    return best, "auto"
