"""Pure-function tests for the peaks endpoint helpers (no network, no app).

Run:  python -m pytest enrich/api/test_peaks.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.routers.terrain import parse_ele, peaks_from_overpass


def test_parse_ele_formats():
    assert parse_ele("1602") == 1602.0
    assert parse_ele("1602.4") == 1602.4
    assert parse_ele("1602 m") == 1602.0
    assert parse_ele("1,602") == 1.602  # decimal comma, the OSM reality
    assert parse_ele(None) is None
    assert parse_ele("unknown") is None
    assert parse_ele(1234) == 1234.0


def test_peaks_from_overpass_filters_and_sorts():
    data = {"elements": [
        {"lat": 50.1, "lon": 14.1, "tags": {"name": "Low", "ele": "400"}},
        {"lat": 50.2, "lon": 14.2, "tags": {"name": "High", "ele": "1602 m"}},
        {"lat": 50.3, "lon": 14.3, "tags": {"ele": "999"}},          # unnamed
        {"lat": 50.4, "lon": 14.4, "tags": {"name": "NoEle"}},        # no ele
        {"tags": {"name": "NoCoords", "ele": "1"}},                   # no lat/lon
    ]}
    out = peaks_from_overpass(data)
    assert [p["name"] for p in out] == ["High", "Low", "NoEle"]  # ele desc, None last
    assert out[0]["ele"] == 1602.0
    assert out[2]["ele"] is None


def test_peaks_from_overpass_caps():
    data = {"elements": [
        {"lat": 50, "lon": 14, "tags": {"name": f"P{i}", "ele": str(i)}}
        for i in range(50)]}
    out = peaks_from_overpass(data, limit=10)
    assert len(out) == 10
    assert out[0]["name"] == "P49"  # tallest kept
