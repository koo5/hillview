"""Worker-side stack loading: rings that don't reach the viewpoint SKIP
(fall through to coarser layers) instead of failing the render — the
"Intersection is empty" class of failures from renders outside the ČÚZK
bbox while its composite is the default stack."""
import numpy as np
import pytest

pytest.importorskip("remoulade")
rasterio = pytest.importorskip("rasterio")

import renderer  # noqa: E402
import worker  # noqa: E402

LAT0, LON0 = 50.0, 14.5


def _write_tif(path, lat0, lon0, n=41, cell=0.001, value=100.0):
    from rasterio.transform import from_origin
    with rasterio.open(str(path), "w", driver="GTiff", width=n, height=n,
                       count=1, dtype="float32", crs="EPSG:4326", nodata=-9999,
                       transform=from_origin(lon0 - n / 2 * cell,
                                             lat0 + n / 2 * cell, cell, cell)) as d:
        d.write(np.full((n, n), value, np.float32), 1)


def test_load_stack_skips_out_of_coverage_ring(tmp_path):
    near = tmp_path / "near.tif"
    far = tmp_path / "far.tif"
    _write_tif(near, LAT0, LON0, value=321.0)
    _write_tif(far, 40.0, 5.0, value=999.0)   # nowhere near the viewpoint
    dem = worker._load_stack(renderer, f"{far}@2000:{near}", LAT0, LON0, 1000.0)
    v = dem.sample(np.array([LAT0]), np.array([LON0]))
    assert v[0] == pytest.approx(321.0)


def test_load_stack_all_layers_out_of_coverage_raises(tmp_path):
    far = tmp_path / "far.tif"
    _write_tif(far, 40.0, 5.0)
    with pytest.raises(RuntimeError, match="no DEM layer covers"):
        worker._load_stack(renderer, str(far), LAT0, LON0, 1000.0)
