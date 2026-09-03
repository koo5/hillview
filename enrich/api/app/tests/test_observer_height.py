from app.geocode import parse_height_m


def test_parse_height_variants():
    assert parse_height_m("25") == 25.0
    assert parse_height_m("25 m") == 25.0
    assert parse_height_m("25.5m") == 25.5
    assert parse_height_m("12,5") == 12.5
    assert parse_height_m("80 ft") == 24.38
    assert parse_height_m("80'") == 24.38
    assert parse_height_m("tall") is None
    assert parse_height_m(None) is None
