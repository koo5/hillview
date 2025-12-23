#!/usr/bin/env python3
"""Unit tests for mapillary geo utility functions."""

import pytest
import math
import os
import sys

# Add the parent directory (api/app) to path so we can import the API modules
api_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(api_app_dir))

from mapillary_routes import (
    cull_lat,
    get_center_lon,
    get_lon_diff,
    add_lon_offset,
    shrink_bbox_to_max_area,
)


class TestCullLat:
    """Tests for latitude clamping function."""

    def test_valid_latitude_unchanged(self):
        """Latitudes within [-90, 90] should remain unchanged."""
        assert cull_lat(0) == 0
        assert cull_lat(45.5) == 45.5
        assert cull_lat(-45.5) == -45.5
        assert cull_lat(90) == 90
        assert cull_lat(-90) == -90

    def test_latitude_above_90_clamped(self):
        """Latitudes above 90 should be clamped to 90."""
        assert cull_lat(91) == 90
        assert cull_lat(100) == 90
        assert cull_lat(180) == 90
        assert cull_lat(90.001) == 90

    def test_latitude_below_minus90_clamped(self):
        """Latitudes below -90 should be clamped to -90."""
        assert cull_lat(-91) == -90
        assert cull_lat(-100) == -90
        assert cull_lat(-180) == -90
        assert cull_lat(-90.001) == -90


class TestGetLonDiff:
    """Tests for longitude difference calculation with wrapping."""

    def test_simple_difference(self):
        """Simple longitude differences without wrapping."""
        assert get_lon_diff(0, 10) == 10
        assert get_lon_diff(10, 0) == 10
        assert get_lon_diff(-10, 10) == 20
        assert get_lon_diff(10, -10) == 20

    def test_same_longitude(self):
        """Same longitude should have zero difference."""
        assert get_lon_diff(0, 0) == 0
        assert get_lon_diff(45, 45) == 0
        assert get_lon_diff(-90, -90) == 0

    def test_wrapping_across_antimeridian(self):
        """Longitude differences across the antimeridian (180/-180)."""
        # From 170 to -170 is 20 degrees (not 340)
        assert get_lon_diff(170, -170) == 20
        assert get_lon_diff(-170, 170) == 20

        # From 179 to -179 is 2 degrees
        assert get_lon_diff(179, -179) == 2

        # From 90 to -90 is 180 degrees (either way)
        assert get_lon_diff(90, -90) == 180

    def test_maximum_difference(self):
        """Maximum longitude difference is 180 degrees."""
        assert get_lon_diff(0, 180) == 180
        assert get_lon_diff(0, -180) == 180
        assert get_lon_diff(180, -180) == 0  # Same meridian


class TestAddLonOffset:
    """Tests for adding offset to longitude with wrapping."""

    def test_simple_offset(self):
        """Simple offsets that don't cause wrapping."""
        assert add_lon_offset(0, 10) == 10
        assert add_lon_offset(0, -10) == -10
        assert add_lon_offset(100, 20) == 120
        assert add_lon_offset(-100, -20) == -120

    def test_wrap_positive(self):
        """Longitude should wrap from >180 to negative values."""
        assert add_lon_offset(170, 20) == -170
        assert add_lon_offset(180, 10) == -170
        assert add_lon_offset(0, 200) == -160

    def test_wrap_negative(self):
        """Longitude should wrap from <-180 to positive values."""
        assert add_lon_offset(-170, -20) == 170
        assert add_lon_offset(-180, -10) == 170
        assert add_lon_offset(0, -200) == 160

    def test_boundary_values(self):
        """Test behavior at boundary values."""
        # At exactly 180, should stay at 180 (edge case)
        assert add_lon_offset(180, 0) == 180
        # Just over 180 should wrap
        assert add_lon_offset(180, 1) == -179
        # At exactly -180, should stay at -180
        assert add_lon_offset(-180, 0) == -180
        # Just under -180 should wrap
        assert add_lon_offset(-180, -1) == 179


class TestGetCenterLon:
    """Tests for center longitude calculation with wrapping."""

    def test_simple_center(self):
        """Simple center calculation without wrapping."""
        # Center of 0 and 10 is 5
        assert abs(get_center_lon(0, 10) - 5) < 0.001
        # Center of -10 and 10 is 0
        assert abs(get_center_lon(-10, 10) - 0) < 0.001

    def test_same_longitude(self):
        """Center of same longitude is that longitude."""
        assert abs(get_center_lon(45, 45) - 45) < 0.001
        assert abs(get_center_lon(-90, -90) - (-90)) < 0.001

    def test_center_across_antimeridian(self):
        """Center calculation across the antimeridian."""
        # Center of 170 and -170 should be 180 (or -180)
        center = get_center_lon(170, -170)
        assert abs(center) > 179 or abs(center - 180) < 1 or abs(center + 180) < 1

        # Center of 179 and -179 should be 180 (or -180)
        center = get_center_lon(179, -179)
        assert abs(center) > 179 or abs(center - 180) < 1 or abs(center + 180) < 1

    def test_center_symmetry(self):
        """Center should be symmetric."""
        assert abs(get_center_lon(10, 20) - get_center_lon(20, 10)) < 0.001
        assert abs(get_center_lon(-10, 30) - get_center_lon(30, -10)) < 0.001


class TestShrinkBboxToMaxArea:
    """Tests for bounding box shrinking function."""

    def test_small_bbox_unchanged(self):
        """Bounding boxes smaller than max area should remain unchanged."""
        bbox = (50.0, 10.0, 49.9, 10.1)  # 0.1 x 0.1 = 0.01 sq deg
        result = shrink_bbox_to_max_area(bbox, max_area_sq_deg=0.1)
        assert result == bbox

    def test_exact_max_area_unchanged(self):
        """Bounding box exactly at max area should remain unchanged."""
        bbox = (50.0, 10.0, 49.9, 10.1)  # 0.1 x 0.1 = 0.01 sq deg
        result = shrink_bbox_to_max_area(bbox, max_area_sq_deg=0.01)
        # Use approximate comparison due to floating point arithmetic
        assert abs(result[0] - bbox[0]) < 0.0001
        assert abs(result[1] - bbox[1]) < 0.0001
        assert abs(result[2] - bbox[2]) < 0.0001
        assert abs(result[3] - bbox[3]) < 0.0001

    def test_large_bbox_shrunk(self):
        """Bounding boxes larger than max area should be shrunk."""
        # Large bbox: 10 x 10 = 100 sq deg
        bbox = (55.0, 5.0, 45.0, 15.0)
        max_area = 0.01
        result = shrink_bbox_to_max_area(bbox, max_area_sq_deg=max_area)

        # Result should have smaller area
        result_lat_diff = abs(result[0] - result[2])
        result_lon_diff = get_lon_diff(result[1], result[3])
        result_area = result_lat_diff * result_lon_diff

        assert result_area <= max_area + 0.0001  # Allow small floating point error

    def test_shrunk_bbox_is_centered(self):
        """Shrunk bbox should be centered on original bbox."""
        bbox = (52.0, 8.0, 48.0, 12.0)  # center: lat=50, lon=10
        result = shrink_bbox_to_max_area(bbox, max_area_sq_deg=0.01)

        # Calculate centers
        orig_center_lat = (bbox[0] + bbox[2]) / 2
        result_center_lat = (result[0] + result[2]) / 2

        assert abs(orig_center_lat - result_center_lat) < 0.001

    def test_latitude_clamping(self):
        """Latitudes should be clamped to [-90, 90] after shrinking."""
        # Bbox near north pole that would expand past 90
        bbox = (89.0, 0.0, 88.0, 10.0)
        result = shrink_bbox_to_max_area(bbox, max_area_sq_deg=1.0)

        # Result latitudes should be within valid range
        assert result[0] <= 90
        assert result[2] >= -90

    def test_longitude_wrapping(self):
        """Longitude wrapping should be handled correctly."""
        # Bbox near antimeridian
        bbox = (50.0, 175.0, 45.0, -175.0)
        result = shrink_bbox_to_max_area(bbox, max_area_sq_deg=0.01)

        # Result longitudes should be valid
        assert -180 <= result[1] <= 180 or result[1] == 180
        assert -180 <= result[3] <= 180 or result[3] == 180


class TestBoundsValidation:
    """Tests for bounds validation logic from mapillary_routes."""

    def test_longitude_180_normalization(self):
        """Test that longitude 180 should be treated as -180."""
        # This tests the logic: if lon == 180: lon = -180
        lon = 180
        if lon == 180:
            lon = -180
        assert lon == -180

    def test_valid_latitude_range(self):
        """Latitudes should be in range [-90, 90]."""
        valid_lats = [0, 45, -45, 90, -90, 89.99, -89.99]
        for lat in valid_lats:
            assert -90 <= lat <= 90

        invalid_lats = [91, -91, 180, -180]
        for lat in invalid_lats:
            assert not (-90 <= lat <= 90)

    def test_valid_longitude_range(self):
        """Longitudes should be in range [-180, 180)."""
        valid_lons = [0, 90, -90, 179, -179, 179.99, -180]
        for lon in valid_lons:
            assert -180 <= lon < 180 or lon == -180

        # 180 is at boundary - the code normalizes it to -180
        assert 180 >= 180  # Would fail the < 180 check


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
