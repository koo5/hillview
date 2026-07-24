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


# ---------------------------------------------------------------------------
# refinement #1+2: observer datum + terrain/surface split
# ---------------------------------------------------------------------------
from renderer import CompositeDem, resolve_eye_elevation  # noqa: E402


def test_resolve_eye_no_gps():
    eye, src = resolve_eye_elevation(500.0, observer_height_m=2.0)
    assert (eye, src) == (502.0, "terrain+eye")


def test_resolve_eye_orthometric_fix():
    """A plausible raw fix (phone at ~eye height) is taken as orthometric."""
    eye, src = resolve_eye_elevation(500.0, gps_altitude_m=501.8)
    assert src == "gps-orthometric" and eye == pytest.approx(501.8)


def test_resolve_eye_ellipsoidal_fix():
    """A fix ~44.5 m above ground is the geoid talking, not a tower — 'auto'
    picks the corrected interpretation because it lands nearer eye height."""
    eye, src = resolve_eye_elevation(500.0, gps_altitude_m=546.0)
    assert src == "gps-ellipsoidal-corrected" and eye == pytest.approx(501.5)


def test_resolve_eye_rozhledna():
    """30 m above ground: the corrected reading would be BELOW ground, so raw
    wins — the lookout-tower case survives the geoid heuristic."""
    eye, src = resolve_eye_elevation(500.0, gps_altitude_m=530.0)
    assert src == "gps-orthometric" and eye == pytest.approx(530.0)


def test_resolve_eye_rejects_nonsense():
    eye, src = resolve_eye_elevation(500.0, gps_altitude_m=900.0)
    assert (eye, src) == (502.0, "gps-rejected")
    eye, src = resolve_eye_elevation(500.0, gps_altitude_m=310.0)
    assert src == "gps-rejected"


def test_resolve_eye_forced_datum():
    eye, src = resolve_eye_elevation(500.0, gps_altitude_m=546.0,
                                     gps_datum="orthometric",
                                     max_above_ground_m=60.0)
    assert src == "gps-orthometric" and eye == pytest.approx(546.0)


def test_composite_dem_fine_over_coarse():
    fine = flat_dem(radius_m=5_000.0, cell_m=100.0, base_elev=100.0)
    coarse = flat_dem(radius_m=60_000.0, cell_m=1_000.0, base_elev=700.0)
    comp = CompositeDem(grids=[fine, coarse])
    inside = comp.sample(np.array([LAT0]), np.array([LON0]))
    plat, plon = destination_point(LAT0, LON0, 90.0, 30_000.0)
    outside = comp.sample(np.array([plat]), np.array([plon]))
    assert inside[0] == pytest.approx(100.0)
    assert outside[0] == pytest.approx(700.0)
    assert comp.cell_size_m(LAT0) == pytest.approx(fine.cell_size_m(LAT0))


def test_render_grounds_on_terrain_not_canopy():
    """Surface model has a 20 m canopy blob at the viewpoint; with a terrain
    grid supplied, the eye sits at 2 m above BARE ground, not atop the trees —
    and the horizon dip shrinks accordingly (√(2h/R') for h=2 vs h=22)."""
    surface = flat_dem(radius_m=30_000.0, cell_m=200.0)
    n = surface.elev.shape[0]
    surface.elev[n // 2, n // 2] += 20.0   # one canopy cell AT the viewpoint
    terrain = flat_dem(radius_m=30_000.0, cell_m=200.0)  # bare earth
    kw = dict(az_start=170, az_end=190, az_step_deg=1.0,
              elev_min_deg=-2.0, elev_max_deg=0.5, elev_step_deg=0.005,
              min_distance_m=500.0,        # march starts beyond the canopy cell
              max_distance_m=25_000.0)
    with_t = render(surface, LAT0, LON0, terrain_dem=terrain, **kw)
    without = render(surface, LAT0, LON0, **kw)
    assert with_t.eye_elevation_m == pytest.approx(2.0, abs=0.3)
    assert without.eye_elevation_m == pytest.approx(22.0, abs=1.0)
    assert with_t.params["eye_source"] == "terrain+eye"
    dip = lambda h: -math.degrees(math.sqrt(2 * h / effective_radius()))  # noqa: E731
    top = lambda p: p.elev_angles[int(np.argmax(np.isfinite(p.depth[:, 5])))]  # noqa: E731
    assert top(with_t) == pytest.approx(dip(2.0), abs=0.02)
    assert top(without) == pytest.approx(dip(22.0), abs=0.02)


def test_geotiff_window_clips_to_extent(tmp_path):
    """Requesting a window larger than the raster must NOT shift the grid:
    the returned georeference has to match a known cell (regression for the
    unclipped-window bug the synthetic E2E caught at a mosaic edge)."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from renderer import load_geotiff_window
    cell = 0.001
    n = 41
    elev = np.zeros((n, n), np.float32)
    elev[5, 30] = 777.0                       # a marker cell NE of center
    path = str(tmp_path / "d.tif")
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1,
                       dtype="float32", crs="EPSG:4326", nodata=-9999,
                       transform=from_origin(LON0 - 20.5 * cell,
                                             LAT0 + 20.5 * cell, cell, cell)) as d:
        d.write(elev, 1)
    dem = load_geotiff_window(path, LAT0, LON0, radius_m=10_000_000)  # way oversized
    marker_lat = LAT0 + (20 - 5) * cell
    marker_lon = LON0 + (30 - 20) * cell
    v = dem.sample(np.array([marker_lat]), np.array([marker_lon]))
    assert v[0] == pytest.approx(777.0)


def test_progress_callback_marches_to_completion():
    """Progress reports the ITERATION fraction of the distance march (each
    step costs the same, so it's an honest wall-clock estimate): strictly
    increasing, ~20 reports, final call exactly 1.0."""
    dem = flat_dem(radius_m=30_000.0)
    seen = []
    render(dem, LAT0, LON0, observer_elevation_m=50.0,
           az_start=0, az_end=5, az_step_deg=0.5,
           elev_min_deg=-2.0, elev_max_deg=1.0, elev_step_deg=0.1,
           max_distance_m=25_000.0, progress=seen.append)
    assert seen, "progress callback never fired"
    assert seen == sorted(seen) and len(seen) == len(set(seen))
    assert seen[-1] == pytest.approx(1.0)
    assert 15 <= len(seen) <= 25
    assert all(0.0 < f <= 1.0 for f in seen)


def test_progress_none_is_default_and_harmless():
    dem = flat_dem(radius_m=10_000.0)
    pano = render(dem, LAT0, LON0, observer_elevation_m=50.0,
                  az_start=0, az_end=2, az_step_deg=1.0,
                  elev_min_deg=-1.0, elev_max_deg=0.5, elev_step_deg=0.25,
                  max_distance_m=8_000.0)
    assert pano.depth.shape[1] == 2


def test_checkpoint_partials_are_prefixes_of_the_final():
    """A milestone partial is a VALID panorama: wherever it sees terrain the
    final sees the SAME depth (the accumulate is monotone — longer marches
    only fill in what was sky), everything it sees lies within the milestone
    distance, and a peak beyond the milestone appears only in the final."""
    # flat ground fills the partial's lower rows (all within 10 km at these
    # angles); the 900 m peak at 22 km exists only in the final
    dem = flat_dem(radius_m=40_000.0, base_elev=0.0)
    add_peak(dem, 90.0, 22_000.0, 900.0)
    partials = []
    final = render(dem, LAT0, LON0, observer_elevation_m=30.0,
                   az_start=85, az_end=95, az_step_deg=0.25,
                   elev_min_deg=-2.0, elev_max_deg=3.0, elev_step_deg=0.05,
                   max_distance_m=30_000.0,
                   checkpoint=lambda p, f: partials.append((p, f)),
                   checkpoint_distances_m=(10_000.0, 90_000.0))  # 2nd skipped
    assert len(partials) == 1, "only the in-range milestone should fire"
    part, frac = partials[0]
    assert 0.0 < frac < 1.0
    vis = np.isfinite(part.depth)
    assert vis.any(), "the near ground must be visible in the partial"
    assert np.isfinite(final.depth[vis]).all()
    np.testing.assert_array_equal(part.depth[vis], final.depth[vis])
    assert float(np.nanmax(part.depth)) <= 10_500.0  # within the milestone (+step)
    grown = np.isfinite(final.depth) & ~vis
    assert grown.any(), "the far peak should appear only in the final"
    assert float(np.nanmin(final.depth[grown])) > 10_000.0
    assert part.meta()["width"] == final.meta()["width"]
