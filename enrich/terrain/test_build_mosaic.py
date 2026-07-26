"""Command-construction tests for build_mosaic.py — no pdal/gdal needed."""
import math
from pathlib import Path

import pytest

from build_mosaic import cog_cmd, pdal_pipeline, vrt_cmd, warp_cmd


def test_pdal_pipeline_kinds():
    dsm = pdal_pipeline(Path("a.laz"), Path("a.tif"), 2.0, "dsm")["pipeline"][1]
    dtm = pdal_pipeline(Path("a.laz"), Path("a.tif"), 2.0, "dtm")["pipeline"][1]
    assert dsm["output_type"] == "max"      # ridge/canopy line preserved
    assert dtm["output_type"] == "idw"
    assert dsm["resolution"] == 2.0 and dsm["nodata"] == -9999


def test_warp_cmd_square_metric_cells():
    cmd = warp_cmd(Path("in.tif"), Path("out.tif"), 30.0, 49.8,
                   "EPSG:5514+8357", "max")
    i = cmd.index("-tr")
    dlon, dlat = float(cmd[i + 1]), float(cmd[i + 2])
    assert dlat * 111_320 == pytest.approx(30.0, rel=1e-6)
    assert dlon * 111_320 * math.cos(math.radians(49.8)) == pytest.approx(30.0, rel=1e-4)
    assert cmd[cmd.index("-t_srs") + 1] == "EPSG:4326"
    assert cmd[cmd.index("-s_srs") + 1] == "EPSG:5514+8357"
    assert cmd[cmd.index("-r") + 1] == "max"


def test_warp_cmd_no_s_srs_by_default():
    cmd = warp_cmd(Path("in.tif"), Path("out.tif"), 30.0, 49.8, None, "bilinear")
    assert "-s_srs" not in cmd


def test_vrt_and_cog_cmds():
    cmd = vrt_cmd([Path("a.tif"), Path("b.tif")], Path("m.vrt"))
    assert cmd[:3] == ["gdalbuildvrt", "-resolution", "highest"]
    assert cmd[-2:] == ["a.tif", "b.tif"]
    assert cog_cmd(Path("m.vrt"), Path("m.tif"))[cog_cmd(Path("m.vrt"), Path("m.tif")).index("-of") + 1] == "COG"
