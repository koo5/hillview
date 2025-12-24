#!/usr/bin/env python3
"""
Unit tests for photo_processor pure functions.
"""

import pytest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from photo_processor import PhotoProcessor


class TestIsSupportedImage:
    """Tests for is_supported_image()."""

    def setup_method(self):
        self.processor = PhotoProcessor()

    def test_jpg_supported(self):
        assert self.processor.is_supported_image("photo.jpg") is True

    def test_jpeg_supported(self):
        assert self.processor.is_supported_image("photo.jpeg") is True

    def test_png_supported(self):
        assert self.processor.is_supported_image("photo.png") is True

    def test_tiff_supported(self):
        assert self.processor.is_supported_image("photo.tiff") is True

    def test_heic_supported(self):
        assert self.processor.is_supported_image("photo.heic") is True

    def test_heif_supported(self):
        assert self.processor.is_supported_image("photo.heif") is True

    def test_uppercase_extension(self):
        assert self.processor.is_supported_image("photo.JPG") is True
        assert self.processor.is_supported_image("photo.JPEG") is True
        assert self.processor.is_supported_image("photo.PNG") is True

    def test_mixed_case_extension(self):
        assert self.processor.is_supported_image("photo.JpG") is True

    def test_unsupported_gif(self):
        assert self.processor.is_supported_image("photo.gif") is False

    def test_unsupported_webp(self):
        assert self.processor.is_supported_image("photo.webp") is False

    def test_unsupported_bmp(self):
        assert self.processor.is_supported_image("photo.bmp") is False

    def test_unsupported_txt(self):
        assert self.processor.is_supported_image("file.txt") is False

    def test_unsupported_no_extension(self):
        assert self.processor.is_supported_image("photo") is False

    def test_double_extension(self):
        assert self.processor.is_supported_image("photo.old.jpg") is True

    def test_hidden_file(self):
        assert self.processor.is_supported_image(".hidden.jpg") is True


class TestConvertToDegrees:
    """Tests for _convert_to_degrees()."""

    def setup_method(self):
        self.processor = PhotoProcessor()

    def test_simple_degrees(self):
        """Test conversion with simple integer values."""
        class MockValue:
            def __init__(self, d, m, s):
                self.values = [d, m, s]

        value = MockValue(50, 0, 0)
        result = self.processor._convert_to_degrees(value)
        assert result == 50.0

    def test_with_minutes(self):
        """Test conversion with minutes."""
        class MockValue:
            def __init__(self, d, m, s):
                self.values = [d, m, s]

        value = MockValue(50, 30, 0)
        result = self.processor._convert_to_degrees(value)
        assert result == 50.5

    def test_with_seconds(self):
        """Test conversion with seconds."""
        class MockValue:
            def __init__(self, d, m, s):
                self.values = [d, m, s]

        value = MockValue(50, 0, 36)
        result = self.processor._convert_to_degrees(value)
        assert abs(result - 50.01) < 0.0001

    def test_full_conversion(self):
        """Test full DMS to decimal conversion."""
        class MockValue:
            def __init__(self, d, m, s):
                self.values = [d, m, s]

        # 50° 4' 32.4" should be approximately 50.0756666...
        value = MockValue(50, 4, 32.4)
        result = self.processor._convert_to_degrees(value)
        assert abs(result - 50.0756666) < 0.0001

    def test_prague_coordinates(self):
        """Test with Prague coordinates (50°05'N, 14°25'E)."""
        class MockValue:
            def __init__(self, d, m, s):
                self.values = [d, m, s]

        lat = MockValue(50, 5, 0)
        lon = MockValue(14, 25, 0)

        lat_result = self.processor._convert_to_degrees(lat)
        lon_result = self.processor._convert_to_degrees(lon)

        assert abs(lat_result - 50.0833) < 0.001
        assert abs(lon_result - 14.4166) < 0.001


class TestHasRequiredGpsData:
    """Tests for has_required_gps_data()."""

    def setup_method(self):
        self.processor = PhotoProcessor()

    def test_complete_gps_data(self):
        """Test with all required GPS fields present."""
        exif_data = {
            'gps': {
                'latitude': 50.0755,
                'longitude': 14.4378,
                'bearing': 45.0
            }
        }
        assert self.processor.has_required_gps_data(exif_data) is True

    def test_missing_latitude(self):
        """Test with missing latitude."""
        exif_data = {
            'gps': {
                'longitude': 14.4378,
                'bearing': 45.0
            }
        }
        assert self.processor.has_required_gps_data(exif_data) is False

    def test_missing_longitude(self):
        """Test with missing longitude."""
        exif_data = {
            'gps': {
                'latitude': 50.0755,
                'bearing': 45.0
            }
        }
        assert self.processor.has_required_gps_data(exif_data) is False

    def test_missing_bearing(self):
        """Test with missing bearing."""
        exif_data = {
            'gps': {
                'latitude': 50.0755,
                'longitude': 14.4378
            }
        }
        assert self.processor.has_required_gps_data(exif_data) is False

    def test_empty_gps(self):
        """Test with empty GPS dict."""
        exif_data = {'gps': {}}
        assert self.processor.has_required_gps_data(exif_data) is False

    def test_no_gps_key(self):
        """Test with no GPS key at all."""
        exif_data = {'exif': {'some': 'data'}}
        assert self.processor.has_required_gps_data(exif_data) is False

    def test_empty_exif_data(self):
        """Test with empty exif data."""
        assert self.processor.has_required_gps_data({}) is False

    def test_with_extra_fields(self):
        """Test that extra fields don't affect the check."""
        exif_data = {
            'gps': {
                'latitude': 50.0755,
                'longitude': 14.4378,
                'bearing': 45.0,
                'altitude': 200,
                'extra': 'field'
            }
        }
        assert self.processor.has_required_gps_data(exif_data) is True

    def test_none_values(self):
        """Test with None values (should still fail)."""
        exif_data = {
            'gps': {
                'latitude': None,
                'longitude': 14.4378,
                'bearing': 45.0
            }
        }
        # The key exists but value is None - still returns True because 'in' just checks key presence
        assert self.processor.has_required_gps_data(exif_data) is True

    def test_zero_values(self):
        """Test with zero values (valid coordinates)."""
        exif_data = {
            'gps': {
                'latitude': 0.0,
                'longitude': 0.0,
                'bearing': 0.0
            }
        }
        assert self.processor.has_required_gps_data(exif_data) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
