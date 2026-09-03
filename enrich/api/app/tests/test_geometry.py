from app.geometry import apply_rect


def test_apply_rect_replaces_geometry_and_drops_stale_bounds():
    t = {"selector": {"type": "RECTANGLE", "geometry": {"x": 0.9, "y": 0.1, "w": 0.01, "h": 0.05,
                                                        "bounds": {"minX": 1, "maxX": 2}}},
         "annotation": "abc"}
    out = apply_rect(t, (0.918, 0.1, 0.01, 0.05))
    assert out["selector"]["geometry"] == {"x": 0.918, "y": 0.1, "w": 0.01, "h": 0.05}
    assert out["annotation"] == "abc"
    assert t["selector"]["geometry"]["x"] == 0.9          # input untouched


def test_apply_rect_passthrough():
    t = {"selector": {"type": "RECTANGLE", "geometry": {"x": 0.5, "y": 0, "w": 0.1, "h": 0.1}}}
    assert apply_rect(t, None) is t
    assert apply_rect(None, (0, 0, 1, 1)) is None
