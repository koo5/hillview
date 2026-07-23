"""Renderer tests on synthetic terrain — no data downloads, no rasterio.

Run:  python -m pytest enrich/terrain/test_renderer.py -q
"""
import math

import numpy as np
import pytest

from renderer import (DemGrid, Panorama, decode_depth_u16, destination_point,
                      effective_radius, encode_depth_u16, render)

LAT0, LON0 = 50.0, 14.5
M_PER_DEG_LAT = 111_320.0


def flat_dem(radius_m=120_000.0, cell_m=200.0, base_elev=0.0):
    n = int(2 * radius_m / cell_m) + 1
    dlat = cell_m / M_PER_DEG_LAT
    dlon = cell_m / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))
    elev = np.full((n, n), base_elev, dtype=np.float32)
    return DemGrid(elev=elev, lat_top=LAT0 + (n // 2) * dlat,
                   lon_left=LON0 - (n // 2) * dlon, dlat=dlat, dlon=dlon)


def add_peak(dem: DemGrid, bearing_deg, distance_m, height_m, sigma_m=800.0):
    plat, plon = destination_point(LAT0, LON0, bearing_deg, distance_m)
    h, w = dem.elev.shape
    rows = dem.lat_top - np.arange(h) * dem.dlat
    cols = dem.lon_left + np.arange(w) * dem.dlon
    dy = (rows[:, None] - plat) * M_PER_DEG_LAT
    dx = (cols[None, :] - plon) * M_PER_DEG_LAT * math.cos(math.radians(LAT0))
    dem.elev += (height_m * np.exp(-(dx**2 + dy**2) / (2 * sigma_m**2))).astype(np.float32)
    return float(plat), float(plon)


def test_flat_plane_horizon_dip():
    """Observer 100 m above a plane: the sky/ground boundary must sit at the
    horizon dip −√(2h/R') — the closed-form signature of the curvature term.
    (Farthest pixel DEPTH is not the horizon distance: each row shows its
    nearest crossing, which quantization pulls short of the tangent point.)"""
    dem = flat_dem()
    h = 100.0
    pano = render(dem, LAT0, LON0, observer_elevation_m=h,
                  az_start=0, az_end=10, az_step_deg=0.5,
                  elev_min_deg=-3.0, elev_max_deg=0.5, elev_step_deg=0.01,
                  max_distance_m=120_000.0)
    dip_deg = -math.degrees(math.sqrt(2 * h / effective_radius()))    # ≈ −0.30°
    top = int(np.argmax(np.isfinite(pano.depth[:, 0])))
    assert pano.elev_angles[top] == pytest.approx(dip_deg, abs=0.03)  # ≤ 3 rows
    assert np.isnan(pano.depth[0]).all()                              # top row: sky
    # visibility still reaches out most of the way to the tangent point
    assert float(np.nanmax(pano.depth)) > 0.7 * math.sqrt(2 * effective_radius() * h)


def test_peak_bearing_depth_and_clickback():
    """A 500 m peak 20 km due east: correct column, correct depth, and the
    pixel→latlon click-back lands on the peak."""
    dem = flat_dem()
    plat, plon = add_peak(dem, 90.0, 20_000.0, 500.0)
    pano = render(dem, LAT0, LON0, observer_elevation_m=52.0,
                  az_start=45, az_end=135, az_step_deg=0.1,
                  elev_min_deg=-2.0, elev_max_deg=3.0, elev_step_deg=0.02,
                  max_distance_m=60_000.0)
    # the summit column: where terrain reaches highest into the sky
    top_rows = np.argmax(np.isfinite(pano.depth), axis=0).astype(float)
    top_rows[~np.isfinite(pano.depth).any(axis=0)] = np.inf
    j = int(np.argmin(top_rows))
    assert pano.azimuths[j] == pytest.approx(90.0, abs=0.5)
    r = int(top_rows[j])
    assert float(pano.depth[r, j]) == pytest.approx(20_000.0, rel=0.05)
    hit = pano.pixel_to_latlon(j, r)
    err_m = math.hypot((hit["lat"] - plat) * M_PER_DEG_LAT,
                       (hit["lon"] - plon) * M_PER_DEG_LAT
                       * math.cos(math.radians(LAT0)))
    assert err_m < 1_500.0        # within the Gaussian peak's shoulder


def test_curvature_and_refraction_angle():
    """Summit apparent angle must match atan((H−eye)/d − d/(2R')) — i.e. the
    render actually applies curvature+refraction, not flat-earth geometry."""
    dem = flat_dem(radius_m=90_000.0, cell_m=300.0)
    H, D = 800.0, 60_000.0
    add_peak(dem, 180.0, D, H, sigma_m=1200.0)
    eye = 2.0
    pano = render(dem, LAT0, LON0, observer_elevation_m=eye,
                  az_start=175, az_end=185, az_step_deg=0.1,
                  elev_min_deg=-1.5, elev_max_deg=1.5, elev_step_deg=0.01,
                  max_distance_m=80_000.0)
    j = int(np.argmin(np.abs(pano.azimuths - 180.0)))
    r = int(np.argmax(np.isfinite(pano.depth[:, j])))
    apparent = pano.elev_angles[r]
    expected = math.degrees(math.atan((H - eye) / D - D / (2 * effective_radius())))
    flat_earth = math.degrees(math.atan((H - eye) / D))
    assert apparent == pytest.approx(expected, abs=0.05)          # ~5 pixel rows
    assert abs(apparent - flat_earth) > 0.15    # and measurably NOT flat-earth


def test_hidden_behind_ridge():
    """A 200 m peak behind a 400 m ridge on the same bearing must not create
    any terrain response beyond the ridge's depth in that column."""
    dem = flat_dem(radius_m=60_000.0, cell_m=200.0)
    add_peak(dem, 0.0, 10_000.0, 400.0, sigma_m=1500.0)
    add_peak(dem, 0.0, 25_000.0, 200.0, sigma_m=800.0)
    pano = render(dem, LAT0, LON0, observer_elevation_m=2.0,
                  az_start=-5, az_end=5, az_step_deg=0.2,
                  elev_min_deg=-1.0, elev_max_deg=3.0, elev_step_deg=0.02,
                  max_distance_m=50_000.0)
    j = int(np.argmin(np.abs(((pano.azimuths + 180) % 360) - 180)))
    col = pano.depth[:, j]
    finite = col[np.isfinite(col)]
    assert (finite < 16_000.0).all()   # nothing visible at the hidden peak's ~25 km


def test_depth_codec_roundtrip():
    depth = np.array([[np.nan, 12.0], [99_000.0, 3.0]], dtype=np.float32)
    out = decode_depth_u16(encode_depth_u16(depth), 2, 2)
    assert np.isnan(out[0, 0])
    assert out[1, 0] == pytest.approx(99_000.0, abs=4.0)
    assert np.isfinite(out[0, 1]) and np.isfinite(out[1, 1])   # sub-scale hits survive


def test_pixel_to_latlon_sky_is_none():
    dem = flat_dem(radius_m=20_000.0, cell_m=500.0)
    pano = render(dem, LAT0, LON0, observer_elevation_m=2.0,
                  az_start=0, az_end=2, az_step_deg=1.0,
                  elev_min_deg=-1, elev_max_deg=5, elev_step_deg=0.5,
                  max_distance_m=15_000.0)
    assert pano.pixel_to_latlon(0, 0) is None                  # top pixel: sky
