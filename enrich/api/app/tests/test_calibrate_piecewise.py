"""fit_piecewise: the linear law plus per-panel shift & scale — what a frame
stitched at the wrong focal length leaves behind. Mirrors theilsen.ts."""
import math

from app.calibrate import fit_piecewise, fit_summary


def synth(shift_right=0.4, scale_right=0.95, seam=0.6, noise=0.0):
    """azimuth law Δ = −45 + 90·x (a 90° pano), except the panel right of
    `seam` is rendered `scale_right`× about its centre and shifted."""
    a, b = -45.0, 90.0
    c = (seam + 1) / 2
    pts = []
    for i in range(24):
        x = 0.02 + i * 0.96 / 23
        if x >= seam:
            d = (a + b * c) + (b * (x - c)) / scale_right + shift_right
        else:
            d = a + b * x
        pts.append({"x": round(x, 4), "delta": round(d + noise * ((i % 3) - 1), 4)})
    return pts


def test_recovers_a_shifted_and_scaled_panel():
    fit = fit_piecewise(synth(), None, [0.6])
    assert fit and fit["model"] == "piecewise"
    assert fit["knots"] == [0.0, 0.6, 1.0]
    # left panel ~neutral, right panel: shift ≈ +0.4°, scale ≈ 0.95. The
    # global Theil-Sen line absorbs a little of the distortion (10 of 24
    # points sit in the bad panel), so the split is approximate — but the
    # COMPOSITE mapping, which is what the overlay consumes, is exact.
    assert abs(fit["hwarp"][0]) < 0.05 and abs(fit["hscale"][0] - 1) < 0.01
    assert abs(fit["hwarp"][1] - 0.4) < 0.12
    assert abs(fit["hscale"][1] - 0.95) < 0.005
    assert fit["rms"] < 0.01
    assert fit["panel_n"] == [14, 10]
    # the plain linear fit cannot: its residuals bow across the seam
    lin = fit_summary(synth(), None)
    assert lin["rms"] > fit["rms"] * 3


def test_panels_without_enough_points_stay_neutral():
    pts = synth()
    # a seam splitting the right panel where only one point falls left of it
    fit = fit_piecewise(pts, None, [0.6, 0.63])
    assert fit["knots"] == [0.0, 0.6, 0.63, 1.0]
    assert fit["panel_n"][1] <= 1
    assert fit["hscale"][1] == 1.0            # one point → shift only
    assert abs(fit["hscale"][2] - 0.95) < 0.005


def test_no_seams_is_the_linear_law_with_one_panel():
    fit = fit_piecewise(synth(shift_right=0, scale_right=1), None, [])
    assert fit["knots"] == [0.0, 1.0]
    assert abs(fit["hwarp"][0]) < 1e-6 and abs(fit["hscale"][0] - 1) < 1e-6
    assert fit["fov"] == 90.0 and abs(fit["centre_bias"]) < 1e-6


def test_seams_are_sorted_and_clamped_to_the_open_interval():
    fit = fit_piecewise(synth(), None, [0.9, 0.6, 0.0, 1.0, 1.5])
    assert fit["knots"] == [0.0, 0.6, 0.9, 1.0]
