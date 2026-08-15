"""Baking a terrain overlay: depth buffer + fit → the graduated JSON.

The invariant these tests defend is that the baked curve is the curve the
curator approved on the bench — so the cases mirror
shared/terrain/overlayFit.test.ts (skyline) and peakLabels.test.ts
(occlusion), and the fit must survive the trip byte-identical.
"""
import json
import math

import numpy as np
import pytest

from app.overlay_export import (build_overlay, col_for_azimuth,
                                bearing_distance, decode_depth,
                                project_labels, skyline_from_depth)

# 4 columns × 6 rows spanning +6..-6° (2° per row), 10 m quanta
META = {"width": 4, "height": 6, "az_start": 0.5, "az_end": 3.5,
        "az_step_deg": 1.0, "elev_max_deg": 6.0, "elev_min_deg": -6.0,
        "lat": 50.0, "lon": 14.5, "depth_scale_m": 10.0,
        "max_distance_m": 100_000.0}

FIT = {"centre_bearing": 2.0, "fov_deg": 90.0, "horizon_pct": 50.0,
       "projection": "equirect", "roll_deg": 0.0, "v_scale": 1.0,
       "visibility_km": None, "warp": [0.0, 0.0]}


def depth_buf(columns, meta=META):
    """column → {skyTop, depths(m)}; rows below repeat the last depth."""
    q = np.zeros((meta["height"], meta["width"]), dtype="<u2")
    for col, prof in columns.items():
        for row in range(prof["skyTop"], meta["height"]):
            i = min(row - prof["skyTop"], len(prof["depths"]) - 1)
            m = prof["depths"][i]
            q[row, col] = round(m / meta["depth_scale_m"])
    return q


def test_topmost_terrain_row_sets_the_elevation():
    q = depth_buf({1: {"skyTop": 2, "depths": [5000]}})
    elev, dist = skyline_from_depth(META, q, None)
    # row 2's centre angle: 6 - 2.5*2 = 1°
    assert elev[1] == 1.0
    assert dist[1] == 5000.0


def test_all_sky_columns_are_nan():
    elev, dist = skyline_from_depth(META, depth_buf({1: {"skyTop": 2, "depths": [5000]}}), None)
    assert math.isnan(elev[0]) and math.isnan(elev[2]) and math.isnan(elev[3])
    assert math.isnan(dist[0])


def test_cutoff_drops_to_the_first_row_within_visibility():
    # far ridge at rows 1-3 (50 km), near ridge from row 4 (5 km)
    q = depth_buf({0: {"skyTop": 1, "depths": [50000, 50000, 50000, 5000]}})
    full, _ = skyline_from_depth(META, q, None)
    fogged, fogged_d = skyline_from_depth(META, q, 10_000)
    assert full[0] == 6 - 1.5 * 2       # row 1 → 3°
    assert fogged[0] == 6 - 4.5 * 2     # row 4 → -3°
    assert fogged[0] < full[0]
    assert fogged_d[0] == 5000.0


def test_nothing_within_the_cutoff_is_nan():
    q = depth_buf({0: {"skyTop": 1, "depths": [50000]}})
    elev, _ = skyline_from_depth(META, q, 10_000)
    assert math.isnan(elev[0])


def test_near_clip_zeros_below_terrain_do_not_become_a_horizon():
    # terrain from row 1, then the near field is clipped away (0) at the
    # bottom — a zero must never be read as "visible terrain here"
    q = depth_buf({0: {"skyTop": 1, "depths": [50000, 40000]}})
    q[5, 0] = 0
    elev, dist = skyline_from_depth(META, q, 100_000)
    assert elev[0] == 6 - 1.5 * 2
    assert dist[0] == 50000.0
    # with a cutoff below everything real, the near-clip zero must not rescue it
    elev2, _ = skyline_from_depth(META, q, 1_000)
    assert math.isnan(elev2[0])


def test_decode_depth_rejects_a_mismatched_buffer():
    try:
        decode_depth(b"\x00\x00", META)
    except ValueError as e:
        assert "meta says" in str(e)
    else:
        raise AssertionError("expected a ValueError")


# --- labels ---------------------------------------------------------------

def destination(lat, lon, bearing_deg, distance_m):
    """Forward geodesic — the inverse of bearing_distance, for placing test
    peaks at an exact azimuth and range."""
    d = distance_m / 6_371_000.0
    br = math.radians(bearing_deg)
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(br))
    lo2 = lo1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(la1),
                           math.cos(d) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180


def peak_at(azimuth_deg, distance_m, name="Peak", **kw):
    lat, lon = destination(META["lat"], META["lon"], azimuth_deg, distance_m)
    return {"name": name, "lat": lat, "lon": lon, "ele": 1000, **kw}


def test_visible_peak_gets_its_summit_row_angle():
    # column 1 (azimuth 1.5°): terrain at 20 km from row 2
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    labels = project_labels(META, q, [peak_at(1.5, 20000, "Vrch")], None)
    assert [m["name"] for m in labels] == ["Vrch"]
    assert labels[0]["elev_deg"] == 1.0
    assert labels[0]["distance_m"] == 20000


def test_occluded_peak_is_dropped():
    # a 5 km ridge fills the column: the 20 km summit is behind it
    q = depth_buf({1: {"skyTop": 2, "depths": [5000]}})
    assert project_labels(META, q, [peak_at(1.5, 20000)], None) == []


def test_peak_beyond_the_fit_cutoff_is_dropped():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    assert project_labels(META, q, [peak_at(1.5, 20000)], 10_000) == []
    assert len(project_labels(META, q, [peak_at(1.5, 20000)], 30_000)) == 1


def test_settlement_distance_caps_apply():
    q = depth_buf({1: {"skyTop": 2, "depths": [50000]}})
    far_village = peak_at(1.5, 50000, "Ves", kind="village", population=300)
    assert project_labels(META, q, [far_village], None) == []


def test_labels_are_ordered_by_priority():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]},
                   2: {"skyTop": 2, "depths": [20000]}})
    minor = peak_at(1.5, 20000, "Minor", prominence=10)
    major = peak_at(2.5, 20000, "Major", prominence=500)
    got = project_labels(META, q, [minor, major], None)
    assert [m["name"] for m in got] == ["Major", "Minor"]


def test_a_populous_town_outranks_a_minor_peak():
    """Settlements and terrain share one priority scale, so a town does not
    get crowded out by every nondescript ridge."""
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]},
                   2: {"skyTop": 2, "depths": [20000]}})
    ridge = peak_at(1.5, 20000, "Ridge", prominence=50)
    town = peak_at(2.5, 20000, "Town", kind="town", population=40_000)
    got = project_labels(META, q, [ridge, town], None)
    assert [m["name"] for m in got] == ["Town", "Ridge"]


def test_bearing_distance_round_trips_with_destination():
    lat, lon = destination(META["lat"], META["lon"], 137.0, 42_000.0)
    b, d = bearing_distance(META["lat"], META["lon"], lat, lon)
    assert abs(b - 137.0) < 0.01
    assert abs(d - 42_000.0) < 1.0


def test_col_for_azimuth_is_the_inverse_of_the_sweep():
    assert col_for_azimuth(META, 0.5) == 0
    assert col_for_azimuth(META, 3.5) == 3
    assert col_for_azimuth(META, 200.0) is None


# --- the document ---------------------------------------------------------

def test_build_overlay_document():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=q.tobytes(),
                        peaks=[peak_at(1.5, 20000, "Vrch")],
                        render_id="r-1", attribution="© somebody",
                        label_attribution="peaks © OpenStreetMap contributors")
    assert doc["version"] == 1
    assert doc["skyline"]["az_start"] == 0.5
    assert doc["skyline"]["az_step"] == 1.0
    assert doc["skyline"]["elev_deg"] == [None, 1.0, None, None]
    assert doc["skyline"]["distance_m"] == [None, 20000, None, None]
    assert [m["name"] for m in doc["labels"]] == ["Vrch"]
    assert doc["render"]["id"] == "r-1"
    assert doc["render"]["max_distance_m"] == 100_000.0
    assert doc["attribution"] == "© somebody"
    assert doc["label_attribution"].startswith("peaks ©")


def test_fit_survives_verbatim():
    """Landing is detected by comparing this sub-object against the exported
    fact — any normalization here would strand the item as forever-pending."""
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=q.tobytes(), peaks=[],
                        render_id="r-1", attribution="x")
    assert doc["fit"] == FIT
    assert (json.dumps(doc["fit"], sort_keys=True, separators=(",", ":"))
            == json.dumps(FIT, sort_keys=True, separators=(",", ":")))


def test_document_is_json_serializable_without_nan():
    """NaN is not JSON: a sky column must serialize as null, or the package
    file becomes unparseable by every strict reader downstream."""
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=q.tobytes(), peaks=[],
                        render_id="r-1", attribution="x")
    text = json.dumps(doc, allow_nan=False)
    assert "NaN" not in text
    assert json.loads(text)["skyline"]["elev_deg"][0] is None


def test_label_attribution_omitted_when_no_labels():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=q.tobytes(), peaks=[],
                        render_id="r-1", attribution="x",
                        label_attribution="peaks © OpenStreetMap contributors")
    assert "label_attribution" not in doc


# --- sweeps that cross north ---------------------------------------------

WRAP_META = {**META, "az_start": 358.5, "az_end": 1.5, "az_step_deg": None,
             "width": 4}


def test_az_step_unwraps_a_sweep_crossing_north():
    """az_end < az_start when the wedge crosses 0°; a naive span/width gives a
    NEGATIVE step and smears the horizon backwards."""
    m = {k: v for k, v in WRAP_META.items() if v is not None}
    from app.overlay_export import az_step_of, azimuth_for_column
    assert az_step_of(m) == pytest.approx(1.0)
    assert azimuth_for_column(m, 0) == pytest.approx(358.5)
    assert azimuth_for_column(m, 2) == pytest.approx(0.5)


def test_depth_ref_always_states_the_step():
    """The reading end must never have to guess it (see above)."""
    from app.overlay_export import depth_ref
    m = {k: v for k, v in WRAP_META.items() if v is not None}
    ref = depth_ref(m, 1234)
    assert ref["az_step_deg"] == pytest.approx(1.0)
    assert ref["bytes"] == 1234
    assert ref["depth_scale_m"] == 10.0


def test_depth_ref_only_when_the_buffer_travels():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    without = build_overlay(fit=FIT, meta=META, depth=q.tobytes(), peaks=[],
                            render_id="r-1", attribution="x")
    with_depth = build_overlay(fit=FIT, meta=META, depth=q.tobytes(), peaks=[],
                               render_id="r-1", attribution="x",
                               depth_gz_bytes=999)
    assert "depth" not in without
    assert with_depth["depth"]["bytes"] == 999


# --- the licence notice is an invariant, not a habit ----------------------

def test_refuses_to_bake_without_attribution():
    """The worker's TERRAIN_ATTRIBUTION defaults to "" and it only writes the
    key when set — so an unconfigured worker yields renders with no notice.
    Graduation is what would publish those, and the viewer's show-it-if-present
    check displays nothing for an empty string: the omission would be silent."""
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    for missing in ("", "   ", None):
        with pytest.raises(ValueError, match="no attribution"):
            build_overlay(fit=FIT, meta=META, depth=q.tobytes(), peaks=[],
                          render_id="r-1", attribution=missing)


def test_bakes_with_a_real_notice():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=q.tobytes(), peaks=[],
                        render_id="r-1",
                        attribution="© ČÚZK · produced using Copernicus WorldDEM-30")
    assert "ČÚZK" in doc["attribution"]
