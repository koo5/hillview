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
                                bearing_distance, decode_depth, depth_blob_header,
                                project_labels, skyline_from_depth)

# 4 columns × 6 rows spanning +6..-6° (2° per row), 10 m quanta
META = {"width": 4, "height": 6, "az_start": 0.5, "az_end": 3.5,
        "az_step_deg": 1.0, "elev_max_deg": 6.0, "elev_min_deg": -6.0,
        "lat": 50.0, "lon": 14.5, "depth_scale_m": 10.0,
        "max_distance_m": 100_000.0}

FIT = {"centre_bearing": 2.0, "fov_deg": 90.0, "horizon_pct": 50.0,
       "projection": "equirect", "roll_deg": 0.0, "v_scale": 1.0,
       "visibility_km": None, "warp": [0.0, 0.0]}


def packed(q, meta=META):
    """The HVD1 wire form of a depth array — what every reader now requires."""
    import struct as _s
    head = b"HVD1" + _s.pack("<HHIIf", 1, 32, int(meta["width"]), int(meta["height"]),
                             float(meta["depth_scale_m"]))
    return head.ljust(32, b"\0") + q.tobytes()


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
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    try:
        decode_depth(packed(q)[:-2], META)            # truncated payload
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
    doc = build_overlay(fit=FIT, meta=META, depth=packed(q),
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


def test_skyline_cut_at_the_default_visibility_labels_baked_to_max():
    """The viewer opens with the fit's visibility (skyline cut there, no
    depth needed) but the labels reach max_visibility_km — capped by the
    render's range — so a fog slider has room without a re-export."""
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]},
                   2: {"skyTop": 2, "depths": [60000]}})
    peaks = [peak_at(1.5, 20000, "Near"), peak_at(2.5, 60000, "Far")]
    fit = {**FIT, "visibility_km": 30.0, "max_visibility_km": 150.0}
    doc = build_overlay(fit=fit, meta=META, depth=packed(q), peaks=peaks,
                        render_id="r", attribution="© test")
    # skyline: column 2's terrain (60 km) is beyond the default → cut
    assert doc["skyline"]["distance_m"][1] == 20000
    assert doc["skyline"]["distance_m"][2] is None
    # labels: both, the far one being inside the max range
    assert sorted(l["name"] for l in doc["labels"]) == ["Far", "Near"]
    # ceiling = min(max, render range) = 100 km here
    assert doc["labels_cutoff_km"] == 100.0
    # no max in the fit → the default 150 km, still capped by the render
    doc2 = build_overlay(fit={**FIT, "visibility_km": 30.0}, meta=META, depth=packed(q),
                         peaks=peaks, render_id="r", attribution="© test")
    assert doc2["labels_cutoff_km"] == 100.0 and len(doc2["labels"]) == 2
    # a max BELOW the default never bakes fewer labels than the default shows
    doc3 = build_overlay(fit={**FIT, "visibility_km": 70.0, "max_visibility_km": 30.0}, meta=META,
                         depth=packed(q), peaks=peaks, render_id="r", attribution="© test")
    assert doc3["labels_cutoff_km"] == 70.0
    assert sorted(l["name"] for l in doc3["labels"]) == ["Far", "Near"]


def test_fit_survives_verbatim():
    """Landing is detected by comparing this sub-object against the exported
    fact — any normalization here would strand the item as forever-pending."""
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=packed(q), peaks=[],
                        render_id="r-1", attribution="x")
    assert doc["fit"] == FIT
    assert (json.dumps(doc["fit"], sort_keys=True, separators=(",", ":"))
            == json.dumps(FIT, sort_keys=True, separators=(",", ":")))


def test_document_is_json_serializable_without_nan():
    """NaN is not JSON: a sky column must serialize as null, or the package
    file becomes unparseable by every strict reader downstream."""
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=packed(q), peaks=[],
                        render_id="r-1", attribution="x")
    text = json.dumps(doc, allow_nan=False)
    assert "NaN" not in text
    assert json.loads(text)["skyline"]["elev_deg"][0] is None


def test_label_attribution_omitted_when_no_labels():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=packed(q), peaks=[],
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
    without = build_overlay(fit=FIT, meta=META, depth=packed(q), peaks=[],
                            render_id="r-1", attribution="x")
    with_depth = build_overlay(fit=FIT, meta=META, depth=packed(q), peaks=[],
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
            build_overlay(fit=FIT, meta=META, depth=packed(q), peaks=[],
                          render_id="r-1", attribution=missing)


def test_bakes_with_a_real_notice():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    doc = build_overlay(fit=FIT, meta=META, depth=packed(q), peaks=[],
                        render_id="r-1",
                        attribution="© ČÚZK · produced using Copernicus WorldDEM-30")
    assert "ČÚZK" in doc["attribution"]


# --- label classes + evidence ---------------------------------------------

# the same grid with an eye height, so the height band can be tested. Row 2
# (centre +1.0°) at 20 km corresponds to ele ≈ 676 m for eye 300 m, k 0.13.
META_EYE = {**META, "eye_elevation_m": 300.0, "refraction_k": 0.13}


def test_summit_needs_the_tight_window_and_the_height_band():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    agrees = peak_at(1.5, 20000, "Vrch", ele=676)
    (m,) = project_labels(META_EYE, q, [agrees], None)
    assert m["class"] == "summit"
    assert abs(m["dh_m"]) < 15                    # metres, ~row centre
    assert m["seen_m"] == 20000 and m["col_offset"] == 0
    # ele says the summit is 1.3 km higher than the rendered top edge: the
    # pixel is a different landform, so the peak is not shown at all
    disagrees = peak_at(1.5, 20000, "Vrch", ele=2000)
    assert project_labels(META_EYE, q, [disagrees], None) == []


def test_wide_window_only_is_mass_and_carries_what_was_seen():
    # terrain at 21 km: outside 300 m + 3 % (900 m), inside 8 m + 6 % (1208 m)
    q = depth_buf({1: {"skyTop": 2, "depths": [21000]}})
    (m,) = project_labels(META_EYE, q, [peak_at(1.5, 20000, "Vrch", ele=676)], None)
    assert m["class"] == "mass"
    assert m["seen_m"] == 21000 and m["distance_m"] == 20000
    # …but mass needs the height band too: a hill 1.3 km lower than the
    # terrain seen near it is a different landform, not its mass
    assert project_labels(META_EYE, q, [peak_at(1.5, 20000, "Vrch", ele=-700)], None) == []


def test_a_summit_outranks_a_mass_claim_of_equal_priority():
    """Two untagged peaks: a nearer hill whose distance only wide-matches
    (mass) and a farther one confirmed as a summit — the summit sorts first,
    so a first-come layouter cannot let the foreground hill thin it out."""
    q = depth_buf({1: {"skyTop": 2, "depths": [21000]},
                   2: {"skyTop": 2, "depths": [21000]}})
    near_mass = peak_at(1.5, 20000, "Kopec", ele=676)          # wide only → mass
    far_summit = peak_at(2.5, 21000, "Vrch", ele=676 + 60)     # tight → summit
    got = project_labels(META_EYE, q, [near_mass, far_summit], None)
    assert [(m["name"], m["class"]) for m in got] == [("Vrch", "summit"), ("Kopec", "mass")]


def test_a_tight_row_below_a_wide_row_wins():
    # skyline at 21 km (wide only), the summit's own edge two rows down
    q = depth_buf({1: {"skyTop": 1, "depths": [21000, 21000, 20000]}})
    # ele ≈ −22 m puts the summit's angle at row 3 (−1.0°) for eye 300 m
    (m,) = project_labels(META_EYE, q, [peak_at(1.5, 20000, "Vrch", ele=-22)], None)
    assert m["seen_m"] == 20000                   # not the 21 km skyline
    assert m["elev_deg"] == 6.0 - 3.5 * 2         # row 3
    assert m["class"] == "summit"


def test_without_an_eye_height_tight_alone_makes_a_summit():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    (m,) = project_labels(META, q, [peak_at(1.5, 20000, "Vrch", ele=2000)], None)
    assert m["class"] == "summit" and m["dh_m"] is None


def test_hidden_notable_settlement_becomes_direction_at_the_occluder():
    # a 5 km ridge from row 2 hides the town at 20 km; population 40k → 324 ≥ 240
    q = depth_buf({1: {"skyTop": 2, "depths": [5000]}})
    town = peak_at(1.5, 20000, "Town", kind="town", population=40_000)
    (m,) = project_labels(META_EYE, q, [town], None)
    assert m["class"] == "direction"
    assert m["seen_m"] == 5000                    # the terrain that hides it
    assert m["elev_deg"] == 1.0                   # its top edge, row 2
    # a small village is simply dropped
    assert project_labels(META_EYE, q, [peak_at(1.5, 20000, "Ves", kind="village", population=300)], None) == []
    # a hidden PEAK is not direction material, however prominent
    assert project_labels(META_EYE, q, [peak_at(1.5, 20000, "Big", prominence=900)], None) == []
    # and a notable town beyond 100 km is not a direction hint either
    far = {**META_EYE, "max_distance_m": 200_000.0}
    q2 = depth_buf({1: {"skyTop": 2, "depths": [5000]}})
    assert project_labels(far, q2, [peak_at(1.5, 150_000, "City", kind="city", population=500_000)], None) == []


def test_a_settlement_is_seen_or_a_direction_hint_never_mass():
    """A hit at a town's distance but not its height is the hill behind the
    town, not the town: no "mass" for settlements."""
    q = depth_buf({1: {"skyTop": 2, "depths": [21000]}})
    town = peak_at(1.5, 20000, "Town", kind="town", population=40_000, ele=200)
    (m,) = project_labels(META_EYE, q, [town], None)
    assert m["class"] == "direction" and m["seen_m"] == 21000
    village = peak_at(1.5, 20000, "Ves", kind="village", population=300, ele=200)
    assert project_labels(META_EYE, q, [village], None) == []
    # tight distance but 1.3 km too low: still not the town
    q2 = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    town2 = peak_at(1.5, 20000, "Town", kind="town", population=40_000, ele=2000)
    (m,) = project_labels(META_EYE, q2, [town2], None)
    assert m["class"] == "direction"
    # the town itself, at its own height: seen
    (m,) = project_labels(META_EYE, q2, [peak_at(1.5, 20000, "Town", kind="town", population=40_000, ele=676)], None)
    assert m["class"] == "summit"


def test_no_direction_label_on_foreground_clutter():
    # a tree 100 m away fills the column: nothing is "behind" it usefully
    q = depth_buf({1: {"skyTop": 0, "depths": [100]}})
    assert project_labels(META_EYE, q, [peak_at(1.5, 20000, "City", kind="city", population=500_000)], None) == []


def test_direction_labels_sort_after_every_visible_one():
    # columns 0-2 hidden by a 5 km ridge (so the ±1 neighbourhood cannot
    # rescue Big), column 3 sees 20 km terrain
    q = depth_buf({0: {"skyTop": 2, "depths": [5000]},
                   1: {"skyTop": 2, "depths": [5000]},
                   2: {"skyTop": 2, "depths": [5000]},
                   3: {"skyTop": 2, "depths": [20000]}})
    hidden_city = peak_at(1.5, 20000, "City", kind="city", population=500_000)
    visible_small = peak_at(3.5, 20000, "Small", prominence=10, ele=676)
    got = project_labels(META_EYE, q, [hidden_city, visible_small], None)
    assert [(m["name"], m["class"]) for m in got] == [("Small", "summit"), ("City", "direction")]


def test_azimuth_neighbourhood_rescues_a_node_one_column_off():
    # own column (1) hidden by a 5 km ridge, column 2 sees 20 km terrain
    q = depth_buf({1: {"skyTop": 2, "depths": [5000]},
                   2: {"skyTop": 2, "depths": [20000]}})
    (m,) = project_labels(META_EYE, q, [peak_at(1.5, 20000, "Edge", ele=676)], None)
    assert m["col_offset"] == 1 and m["class"] == "summit"


def test_one_label_per_depth_pixel_keeps_the_higher_priority():
    q = depth_buf({1: {"skyTop": 2, "depths": [20000]}})
    a = peak_at(1.5, 20000, "Turm A", ele=676)
    b = peak_at(1.5, 20000, "Turm B", ele=676, prominence=40)
    got = project_labels(META_EYE, q, [a, b], None)
    assert [m["name"] for m in got] == ["Turm B"]


# --- the HVD1 depth buffer -------------------------------------------------

def _packed(values, width, height, scale=4.0):
    import struct as _s
    body = np.array(values, dtype="<u2").tobytes()
    head = b"HVD1" + _s.pack("<HHIIf", 1, 32, width, height, scale)
    return head.ljust(32, b"\0") + body


def test_decode_reads_the_container():
    packed = _packed([[0, 1234], [65535, 7]], 2, 2)
    assert packed[:4] == b"HVD1" and packed[:3] != b"\x1f\x8b\x08"
    assert packed[20:32] == b"\0" * 12                      # reserved, zeroed
    assert depth_blob_header(packed) == {"version": 1, "header_bytes": 32, "width": 2,
                                         "height": 2, "scale_m": 4.0}
    assert decode_depth(packed, {"width": 2, "height": 2}).tolist() == [[0, 1234], [65535, 7]]


def test_decode_refuses_headerless_and_mismatched_buffers():
    bare = np.zeros(4, dtype="<u2").tobytes()
    assert depth_blob_header(bare) is None
    for buf, meta, msg in (
        (bare, {"width": 2, "height": 2}, "no HVD1 header"),
        (_packed([[0, 0], [0, 0]], 2, 2), {"width": 4, "height": 1}, "meta says 4×1"),
        (_packed([[0, 0], [0, 0]], 2, 2)[:-2], {"width": 2, "height": 2}, "3 samples"),
    ):
        try:
            decode_depth(buf, meta)
        except ValueError as e:
            assert msg in str(e)
        else:
            raise AssertionError(f"expected a ValueError ({msg})")


def test_container_survives_the_gzip_collision_sample():
    """A bare buffer whose first sample is 0x8B1F reads as gzip; with the
    header it starts with "HVD1" and a reader never has to guess."""
    assert np.array([0x8B1F], dtype="<u2").tobytes()[:2] == b"\x1f\x8b"
    packed = _packed([[0x8B1F, 0x0008]], 2, 1)
    assert packed[:3] != b"\x1f\x8b\x08"
    assert decode_depth(packed, {"width": 2, "height": 1}).tolist() == [[0x8B1F, 0x0008]]
