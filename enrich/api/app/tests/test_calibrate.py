"""Circular-aware calibration fit: Δ wraps at ±180 inside wide panos."""
from app import calibrate


def _pano_points(n=12, fov=360.0, centre_bias=0.0):
    # true law: delta = centre_bias + fov·(x − 0.5), stored normalised to ±180
    # x inset from the edges: at exactly ±180° the fold is ambiguous by design
    return [{"x": x, "delta": calibrate.ang_norm(centre_bias + fov * (x - 0.5))}
            for x in [0.02 + 0.96 * i / (n - 1) for i in range(n)]]


def test_no_wrap_when_compass_points_at_the_centre():
    pts = _pano_points(centre_bias=0.0)
    assert calibrate.unwrap_deltas(pts, 409945, 10801) == 0
    fit = calibrate.fit_summary(pts, 100.0)
    assert abs(fit["fov"] - 360) < 1 and fit["rms"] < 0.1


def test_unwrap_recovers_a_360_pano_whose_compass_is_off_centre():
    # Δ crosses ±180 in the middle of the image: half the points on each
    # branch, so even Theil-Sen's median slope is nonsense before unwrapping
    pts = _pano_points(centre_bias=180.0)
    naive = calibrate.fit_summary([dict(p) for p in pts], 100.0)
    assert abs(naive["fov"] - 360) > 30 or naive["rms"] > 30
    n = calibrate.unwrap_deltas(pts, 409945, 10801)
    assert n > 0
    fit = calibrate.fit_summary(pts, 100.0)
    assert abs(fit["fov"] - 360) < 1 and fit["rms"] < 0.1
    assert abs(calibrate.ang_norm(fit["centre_bias"] - 180)) < 1


def test_ordinary_photo_is_untouched():
    pts = _pano_points(n=6, fov=60.0, centre_bias=20.0)
    assert calibrate.unwrap_deltas(pts, 4000, 3000) == 0
    fit = calibrate.fit_summary(pts, 10.0)
    assert abs(fit["fov"] - 60) < 1


def test_residuals_are_circular():
    pts = _pano_points(centre_bias=170.0)
    calibrate.unwrap_deltas(pts, 409945, 10801)
    fit = calibrate.fit_summary(pts, 0.0)
    assert all(abs(p["residual"]) < 1 for p in pts) and fit["rms"] < 0.1
