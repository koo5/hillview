"""Sight-ray triangulation: intersect the bearing lines of several annotations
that depict the same POI to estimate where that POI actually stands.

Each ray is (origin lat/lon, azimuth) where azimuth is a compass bearing
(0 = north, 90 = east, clockwise) — the same convention the calibration/ray
machinery already produces from a rect's x-position. Distances are small enough
(a city) to use a local east-north planar approximation; the least-squares point
minimizes the summed perpendicular distance to every ray-line.
"""
import math

_M_PER_DEG = 111320.0


def _enu(lat, lon, ref_lat, ref_lon):
    x = (lon - ref_lon) * _M_PER_DEG * math.cos(math.radians(ref_lat))
    y = (lat - ref_lat) * _M_PER_DEG
    return x, y


def _latlon(x, y, ref_lat, ref_lon):
    lat = ref_lat + y / _M_PER_DEG
    lon = ref_lon + x / (_M_PER_DEG * math.cos(math.radians(ref_lat)))
    return lat, lon


def triangulate(rays: list[dict]) -> dict | None:
    """rays: [{lat, lon, azimuth, ...}]. Returns None if fewer than two usable
    rays or they're parallel (no intersection). Otherwise:
      {lat, lon, residual_m, rays: [{..., forward_m}]}
    forward_m > 0 means the estimate is in front of that camera (good geometry);
    a negative value means the rays only meet *behind* it (bad pairing).
    residual_m is the RMS perpendicular miss — the tightness of the fix."""
    rays = [r for r in rays
            if r.get("lat") is not None and r.get("lon") is not None
            and r.get("azimuth") is not None]
    if len(rays) < 2:
        return None

    ref_lat = sum(r["lat"] for r in rays) / len(rays)
    ref_lon = sum(r["lon"] for r in rays) / len(rays)

    # normal equations for min Σ |(I - d dᵀ)(x - p)|²  →  A x = b
    a00 = a01 = a11 = b0 = b1 = 0.0
    prepped = []
    for r in rays:
        px, py = _enu(r["lat"], r["lon"], ref_lat, ref_lon)
        az = math.radians(r["azimuth"])
        dx, dy = math.sin(az), math.cos(az)  # bearing → east/north unit vector
        pxx, pxy, pyy = 1 - dx * dx, -dx * dy, 1 - dy * dy
        a00 += pxx
        a01 += pxy
        a11 += pyy
        b0 += pxx * px + pxy * py
        b1 += pxy * px + pyy * py
        prepped.append((px, py, dx, dy))

    det = a00 * a11 - a01 * a01
    if abs(det) < 1e-9:  # rays parallel
        return None
    x = (a11 * b0 - a01 * b1) / det
    y = (a00 * b1 - a01 * b0) / det
    lat, lon = _latlon(x, y, ref_lat, ref_lon)

    sq = 0.0
    ray_out = []
    for (px, py, dx, dy), r in zip(prepped, rays):
        t = (x - px) * dx + (y - py) * dy          # forward distance along ray
        cx, cy = px + t * dx, py + t * dy           # closest point on the ray-line
        miss = math.hypot(x - cx, y - cy)
        sq += miss * miss
        ray_out.append({**r, "forward_m": round(t)})

    return {"lat": round(lat, 6), "lon": round(lon, 6),
            "residual_m": round(math.sqrt(sq / len(rays)), 1),
            "rays": ray_out}
