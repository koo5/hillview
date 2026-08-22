"""Unit tests for the terrain-overlay graduation helpers.

The load-bearing property: an overlay is compared by its FIT ALONE. The baked
skyline changes whenever the photo is re-rendered, and hillview's own
fine-tuning lives in user_adjust — comparing either would make settled
overlays look permanently out of date to the workbench and re-offer them
forever.
"""
import graduation


FIT = {"centre_bearing": 163.1, "fov_deg": 189.8, "horizon_pct": 30.3,
       "projection": "equirect", "roll_deg": 0.0, "v_scale": 1.0,
       "visibility_km": None, "warp": [0.8356, -0.9034, 0.3528]}


def overlay(fit=None, **kw):
    return {"version": 1, "fit": fit or FIT,
            "skyline": {"az_start": 60.0, "az_step": 0.05,
                        "elev_deg": [1.0, None, 2.0]},
            "labels": [{"name": "Říp"}],
            "render": {"id": "r-1"},
            "attribution": "produced using Copernicus WorldDEM-30 …",
            **kw}


def test_canonical_fit_is_key_order_independent():
    a = graduation.canonical_fit({"a": 1, "b": 2})
    b = graduation.canonical_fit({"b": 2, "a": 1})
    assert a == b


def test_canonical_fit_of_nothing_is_none():
    assert graduation.canonical_fit(None) is None
    assert graduation.canonical_fit({}) is None


def test_classify_clean_when_hillview_matches_what_the_workbench_saw():
    proposed = graduation.canonical_fit(FIT)
    assert graduation.classify_overlay(None, None, proposed, True) == "clean"


def test_classify_already_applied_only_when_the_whole_document_matches():
    fit = graduation.canonical_fit(FIT)
    assert graduation.classify_overlay(
        fit, fit, fit, True, payload_equal=True) == "already_applied"
    # same alignment, different document (a re-render) is still work to do —
    # and it is clean, because hillview's alignment is what the workbench saw
    assert graduation.classify_overlay(
        fit, fit, fit, True, payload_equal=False) == "clean"


def test_classify_conflict_when_hillview_moved_on():
    other = graduation.canonical_fit({**FIT, "horizon_pct": 44.0})
    proposed = graduation.canonical_fit(FIT)
    assert graduation.classify_overlay(None, other, proposed, True) == "conflict"


def test_classify_missing_photo():
    assert graduation.classify_overlay(None, None, "x", False) == "missing"


# --- payload comparison (the apply-side "already applied" question) --------

def with_depth(ov, ident, *, stored: bool):
    """The same depth reference as a package op sees it (blob hash) vs as a
    stored document holds it (a pool URL)."""
    ref = {"width": 4152, "height": 690, "depth_scale_m": 4.0}
    ref.update({"url": f"https://pics.example/terrain/{ident}.depth.bin.gz"}
               if stored else {"blob": ident})
    return {**ov, "depth": ref}


def test_payload_equal_across_the_blob_to_url_rewrite():
    """Apply rewrites the depth handle into a URL; that rewrite alone must not
    make every re-apply look like a change."""
    proposed = with_depth(overlay(), "abc123", stored=False)
    stored = with_depth(overlay(), "abc123", stored=True)
    assert graduation.overlay_payload_equal(stored, proposed)


def test_payload_differs_when_the_depth_buffer_changed():
    proposed = with_depth(overlay(), "newhash", stored=False)
    stored = with_depth(overlay(), "oldhash", stored=True)
    assert not graduation.overlay_payload_equal(stored, proposed)


def test_payload_ignores_local_user_adjust():
    stored = overlay(user_adjust={"horizon_pct_delta": -2.5})
    assert graduation.overlay_payload_equal(stored, overlay())


def test_a_rerender_with_the_same_fit_is_still_applicable():
    """The whole point: a better elevation model changes the skyline but not
    the alignment, and that improvement has to be publishable."""
    stored = overlay()
    fresh = overlay()
    fresh["skyline"] = {"az_start": 60.0, "az_step": 0.025,
                        "elev_deg": [1.0, 1.5, None, 2.0, 2.5]}
    assert (graduation.canonical_fit(stored["fit"])
            == graduation.canonical_fit(fresh["fit"]))
    assert not graduation.overlay_payload_equal(stored, fresh)


def test_payload_equal_is_false_when_there_is_nothing_stored():
    assert not graduation.overlay_payload_equal(None, overlay())


def test_fit_comparison_ignores_the_baked_skyline():
    """Re-rendering a photo at a different grid changes every skyline sample
    but not the fit — that must still read as already applied."""
    stored = overlay()
    fresh = overlay()
    fresh["skyline"] = {"az_start": 60.0, "az_step": 0.025,
                        "elev_deg": [1.0, 1.5, None, 2.0, 2.5]}
    fresh["labels"] = []
    assert (graduation.canonical_fit(stored["fit"])
            == graduation.canonical_fit(fresh["fit"]))


def test_fit_comparison_ignores_local_user_adjust():
    """A hillview-side horizon nudge must never resurrect a landed item — the
    fit is what the WORKBENCH compares, and user_adjust is outside it."""
    stored = overlay(user_adjust={"horizon_pct_delta": -2.5})
    proposed = overlay()
    assert (graduation.canonical_fit(stored["fit"])
            == graduation.canonical_fit(proposed["fit"]))


def test_overlay_stats_counts_visible_points_not_samples():
    s = graduation.overlay_stats(overlay())
    assert s["samples"] == 3
    assert s["points"] == 2      # the None is sky, not a horizon point
    assert s["labels"] == 1
    assert s["projection"] == "equirect"
    assert s["render_id"] == "r-1"


def test_overlay_stats_surfaces_the_attribution_for_review():
    """The reviewer is about to start publishing this notice — it has to be
    visible at review time, not buried in the document."""
    s = graduation.overlay_stats(overlay())
    assert "Copernicus" in s["attribution"]


def test_overlay_stats_of_nothing_is_empty():
    assert graduation.overlay_stats(None) == {}
