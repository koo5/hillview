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


def unwrap_deltas(points: list[dict], width, height, prior_fov: float | None = None) -> int:
    """Δ (candidate azimuth − compass) is stored normalised to −180…180. On a
    pano whose FOV exceeds 180° with the compass pointing away from the image
    centre, Δ crosses ±180 INSIDE the image and a straight-line fit sees a 360°
    jump. Unwrap in place: predict each point from the one nearest x = 0.5
    using an FOV prior — the pano's accepted calibration when it has one, else
    the aspect-ratio guess (DEG_PER_ASPECT·2 per unit, 60…360°; crude: a 31:1
    crop has measured 166° and a 38:1 one 360°) — and add ±360 where the stored
    Δ is more than 180° from that prediction. Points that don't wrap are
    untouched (k = 0). → number of points unwrapped."""
    if len(points) < 2:
        return 0
    if not prior_fov:
        try:
            aspect = float(width) / float(height)
        except (TypeError, ZeroDivisionError, ValueError):
            return 0
        prior_fov = min(360.0, max(60.0, aspect * DEG_PER_ASPECT * 2))
    ref = min(points, key=lambda p: abs(p["x"] - 0.5))
    n = 0
    for p in points:
        pred = ref["delta"] + prior_fov * (p["x"] - ref["x"])
        k = round((pred - p["delta"]) / 360.0)
        if k:
            p["delta_raw"] = p["delta"]
            p["delta"] = p["delta"] + 360.0 * k
            n += 1
    return n


def fit_summary(points: list[dict], compass: float | None) -> dict | None:
    """points: [{x, delta}] (delta vs compass). → fit params + per-point residuals."""
    if len(points) < 2:
        return None
    fit = theil_sen([p["x"] for p in points], [p["delta"] for p in points])
    if not fit:
        return None
    a, b = fit
    for p in points:
        p["residual"] = round(ang_norm(p["delta"] - (a + b * p["x"])), 2)
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


def fit_piecewise(points: list[dict], compass: float | None,
                  seams: list[float]) -> dict | None:
    """Stitched-pano model: the linear law (Theil-Sen, as fit_summary) PLUS a
    per-PANEL shift and scale, panels being the pieces between the given
    seams (fractions of the width, 0 < s < 1). What a frame stitched at the
    wrong focal length leaves behind is exactly this: within its region the
    azimuth runs at a different rate (scale) and is displaced (shift), while
    the rest of the pano is fine.

    Per panel the residual against the global line is fitted robustly as
    r = shift + d·(x − centre) (Theil-Sen; one point → shift only; none →
    neutral). In the overlay projector's terms (shared/terrain/overlayFit.ts,
    `hwarp`/`hscale`/`knots`): hwarp[k] = shift (the pano shows an azimuth
    that much HIGHER there), hscale[k] = b/(b + d) (the panel's content is
    rendered that much larger than the ideal law), knots = [0, *seams, 1].
    Emits fov/centre_bearing like the linear fit, so consumers that only
    want the pie are unchanged."""
    if len(points) < 2:
        return None
    base = theil_sen([p["x"] for p in points], [p["delta"] for p in points])
    if not base:
        return None
    a, b = base
    if abs(b) < 1e-9:
        return None
    knots = [0.0] + sorted(s for s in seams if 0.0 < s < 1.0) + [1.0]
    n = len(knots)
    hwarp = [0.0] * n
    hscale = [1.0] * n
    panel_n = [0] * (n - 1)
    for k in range(n - 1):
        lo, hi = knots[k], knots[k + 1]
        last = k == n - 2
        pk = [p for p in points if lo <= p["x"] < hi or (last and p["x"] == hi)]
        panel_n[k] = len(pk)
        if not pk:
            continue
        c = (lo + hi) / 2
        rs = [p["delta"] - (a + b * p["x"]) for p in pk]
        if len(pk) >= 2 and len({p["x"] for p in pk}) >= 2:
            ts = theil_sen([p["x"] - c for p in pk], rs)
            shift, d = ts if ts else (sorted(rs)[len(rs) // 2], 0.0)
        else:
            shift, d = rs[0], 0.0
        scale = b / (b + d) if b + d != 0 else 1.0
        hwarp[k] = round(shift, 3)
        hscale[k] = round(min(2.0, max(0.5, scale)), 5)

    def predict(x: float) -> float:
        k = 0
        while k < n - 2 and x >= knots[k + 1]:
            k += 1
        c = (knots[k] + knots[k + 1]) / 2
        # true(x) = ideal(c) + (ideal(x) − ideal(c))/scale + shift
        return (a + b * c) + (b * (x - c)) / hscale[k] + hwarp[k]

    for p in points:
        p["residual"] = round(ang_norm(p["delta"] - predict(p["x"])), 2)
    rms = math.sqrt(sum(p["residual"] ** 2 for p in points) / len(points))
    centre_bias = a + b * 0.5
    return {
        "model": "piecewise",
        "intercept": round(a, 2), "slope": round(b, 2),
        "fov": round(abs(b), 1),
        "centre_bias": round(centre_bias, 2),
        "centre_bearing": (round((compass + centre_bias) % 360, 2)
                           if compass is not None else None),
        "rms": round(rms, 2),
        "n": len(points),
        "knots": [round(k, 5) for k in knots],
        "hwarp": hwarp,
        "hscale": hscale,
        "panel_n": panel_n,
    }


def fit_rectilinear(points: list[dict], compass: float | None) -> dict | None:
    """Rectilinear (f0) model: delta(x) = c + atan(k·(x − x0)), degrees — for
    panos whose stitch OUTPUT projection is rectilinear (a straight line fit
    bows on those: ends one sign, middle the other; see
    docs/pano-source-archaeology.md). Coarse (x0, k) grid + local refinement;
    c is the median offset, the robust mirror of the Theil-Sen intercept.
    Reported fov = azimuth SPAN across the full width, so pie consumers keep
    their semantics; x0 is the projection centre (principal point x)."""
    if len(points) < 4:
        return None
    xs = [p["x"] for p in points]
    ys = [p["delta"] for p in points]

    def eval_at(x0: float, k: float) -> tuple[float, float]:
        at = [math.degrees(math.atan(k * (x - x0))) for x in xs]
        r = sorted(y - a for y, a in zip(ys, at))
        c = r[len(r) // 2]
        return c, sum((y - c - a) ** 2 for y, a in zip(ys, at))

    best: tuple[float, float, float, float] | None = None  # (sse, x0, k, c)

    def consider(x0: float, k: float) -> None:
        nonlocal best
        if k <= 0.05:
            return
        c, s = eval_at(x0, k)
        if best is None or s < best[0]:
            best = (s, x0, k, c)

    for i in range(-25, 76):              # x0: −0.5 … 1.5, step 0.02
        for j in range(2, 81):            # k: 0.2 … 8, step 0.1
            consider(i * 0.02, j * 0.1)
    dx, dk = 0.02, 0.1
    for _ in range(3):
        _, bx0, bk, _ = best
        for i in range(-5, 6):
            for j in range(-5, 6):
                consider(bx0 + i * dx / 5, bk + j * dk / 5)
        dx /= 5
        dk /= 5

    sse, x0, k, c = best
    for p in points:
        p["residual"] = round(
            ang_norm(p["delta"] - (c + math.degrees(math.atan(k * (p["x"] - x0))))), 2)
    rms = math.sqrt(sse / len(points))
    fov = math.degrees(math.atan(k * (1 - x0)) - math.atan(k * (0 - x0)))
    centre_bias = c + math.degrees(math.atan(k * (0.5 - x0)))
    return {
        "model": "rectilinear",
        "intercept": round(c, 2), "x0": round(x0, 4), "k": round(k, 4),
        "slope": round(math.degrees(k), 2),   # d(delta)/dx at x0, °/x
        "fov": round(fov, 1),
        "centre_bias": round(centre_bias, 2),
        "centre_bearing": (round((compass + centre_bias) % 360, 2)
                           if compass is not None else None),
        "rms": round(rms, 2),
        "n": len(points),
    }


AUTO_TOL_DEG = 20.0   # auto-pick vs a predicted azimuth: max |bearing − predicted|
DEG_PER_ASPECT = 4.8  # half-FOV guess per unit of aspect ratio: measured panos give
                      # 253° at 26:1 and 360° at 38:1 → ≈ 9.6° of FOV per unit, half = 4.8


def half_window_for(width, height) -> tuple[float, str]:
    """Compass half-window when nothing better is known: ±TOL_DEG for ordinary
    photos, widened by the aspect ratio for panos (26:1 → ±125°, 38:1 → ±180°).
    → (deg, basis text for the UI)."""
    try:
        aspect = float(width) / float(height)
    except (TypeError, ZeroDivisionError, ValueError):
        return TOL_DEG, f"compass ±{TOL_DEG:.0f}°"
    half = min(180.0, max(TOL_DEG, aspect * DEG_PER_ASPECT))
    basis = (f"compass ±{half:.0f}° (widened for the {aspect:.0f}:1 pano)"
             if half > TOL_DEG else f"compass ±{TOL_DEG:.0f}°")
    return half, basis


def pick_anchor(candidates: list[dict], photo_lon, photo_lat, compass,
                importance: dict[str, float], rect_x: float | None = None,
                predict=None, predict_basis: str = "",
                half_window: float = TOL_DEG,
                window_basis: str = "") -> tuple[dict | None, str, str]:
    """Choose one anchor per annotation and say why. Order: approved > pinned
    (geo: coordinates the annotator gave) > wikipedia > auto. Auto picks among
    the Nominatim hits within the distance ceiling: with `predict` (rect_x →
    expected Δ vs compass, from the pano's calibration or a fit of its trusted
    anchors) the hit nearest the predicted azimuth wins if within AUTO_TOL_DEG;
    otherwise the most important hit inside the compass half-window.
    → (candidate|None, rule, why)."""
    located = [c for c in candidates if c.get("lat") is not None]
    if not located:
        return None, "none", "no candidate with coordinates"
    approved = [c for c in located if c["status"] == "approved"]
    if approved:
        return approved[0], "approved", "approved by the curator"
    nonrejected = [c for c in located if c["status"] != "rejected"]
    if not nonrejected:
        return None, "all-rejected", "every candidate was rejected"
    # a candidate is the annotation's OWN unless it was only borrowed from a
    # namesake (seeded_from and not own)
    def borrowed(c):
        return bool(c.get("seeded_from")) and not c.get("own")
    # geo: candidates = author/curator-given points (body-embedded coords, a
    # lat/lon-only hillview link, or map pins); strongest un-curated signal
    pinned = [c for c in nonrejected if c["candidate"].startswith("geo:") and not borrowed(c)]
    if pinned:
        return pinned[0], "pinned", "coordinates given by the annotator (body / link / pin)"
    wiki = [c for c in nonrejected if "wikipedia.org" in c["candidate"] and not borrowed(c)]
    if wiki:
        return wiki[0], "wikipedia", "coordinates of the linked wikipedia page"

    def db_of(c):
        return ang_norm(bearing_deg(photo_lon, photo_lat, c["lon"], c["lat"]) - compass)

    # namesake seeds: another annotation's own anchor for the same label / id=
    # key — trusted above Nominatim, but only if the geometry agrees (a "hl.n."
    # elsewhere is a different station); generous distance ceiling, the source
    # annotator vouched for the place
    seeds = [c for c in nonrejected if borrowed(c)
             and MIN_KM <= haversine_km(photo_lon, photo_lat, c["lon"], c["lat"]) <= PEAK_KM]
    if seeds and compass is not None:
        def src_text(c):
            s = (c.get("seeded_from") or [{}])[0]
            what = "their coordinates" if c["candidate"].startswith("geo:") else "their anchor"
            return f"namesake ‘{s.get('label') or '?'}’ on {s.get('photo_title') or 'another photo'} ({what})"
        if predict is not None and rect_x is not None:
            expected = predict(rect_x)
            best = min(seeds, key=lambda c: abs(ang_norm(db_of(c) - expected)))
            err = abs(ang_norm(db_of(best) - expected))
            if err <= AUTO_TOL_DEG:
                return best, "namesake", (f"{src_text(best)}: off by {err:.0f}° from the azimuth "
                                          f"predicted for the rect ({predict_basis})")
        else:
            inside = [c for c in seeds if abs(db_of(c)) <= half_window]
            if inside:
                best = min(inside, key=lambda c: abs(db_of(c)))
                return best, "namesake", (f"{src_text(best)}: inside "
                                          f"{window_basis or f'compass ±{half_window:.0f}°'}")
    pool, too_far = [], 0
    for c in nonrejected:
        km = haversine_km(photo_lon, photo_lat, c["lon"], c["lat"])
        if MIN_KM <= km <= kind_ceiling(c.get("osmType")):
            pool.append(c)
        else:
            too_far += 1
    if not pool:
        return None, "no-in-view", (f"{len(nonrejected)} Nominatim hit(s), all outside the "
                                    f"distance ceiling ({NEAR_KM:.0f} km places / "
                                    f"{PEAK_KM:.0f} km peaks)")
    if compass is None:
        best = max(pool, key=lambda c: importance.get(c["candidate"], 0.0))
        return best, "auto", f"most important of {len(pool)} hit(s); photo has no compass"
    if predict is not None and rect_x is not None:
        expected = predict(rect_x)
        scored = sorted(pool, key=lambda c: abs(ang_norm(db_of(c) - expected)))
        best, err = scored[0], abs(ang_norm(db_of(scored[0]) - expected))
        if err <= AUTO_TOL_DEG:
            return best, "auto", (f"nearest to the azimuth predicted for the rect "
                                  f"({predict_basis}): off by {err:.0f}°"
                                  + (f", {len(pool) - 1} other hit(s) further off"
                                     if len(pool) > 1 else ""))
        return None, "no-in-view", (f"{len(pool)} hit(s) within distance, but the closest is "
                                    f"{err:.0f}° from the azimuth predicted for the rect "
                                    f"({predict_basis}; limit {AUTO_TOL_DEG:.0f}°)")
    inside = [c for c in pool if abs(db_of(c)) <= half_window]
    basis = window_basis or f"compass ±{half_window:.0f}°"
    if not inside:
        return None, "no-in-view", f"{len(pool)} hit(s) within distance but none inside {basis}"
    best = max(inside, key=lambda c: importance.get(c["candidate"], 0.0))
    why = f"most important of {len(inside)} hit(s) inside {basis}"
    if too_far:
        why += f"; {too_far} beyond the distance ceiling"
    return best, "auto", why
