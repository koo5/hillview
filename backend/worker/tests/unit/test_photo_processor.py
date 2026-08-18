#!/usr/bin/env python3
"""
Unit tests for photo_processor pure functions.
"""

import json
import pytest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from photo_processor import AnonymizationOverride, PhotoProcessor



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


class TestAnonymizationOverride:
    """Tests for AnonymizationOverride.from_json_string() mode selection."""

    def test_none_means_auto(self):
        assert AnonymizationOverride.from_json_string(None) is None

    def test_empty_list_means_skip(self):
        override = AnonymizationOverride.from_json_string("[]")
        assert override is not None
        assert override.skip_anonymization is True
        assert override.detections is None

    def test_rectangle_list(self):
        override = AnonymizationOverride.from_json_string(
            '[{"x": 1, "y": 2, "width": 3, "height": 4}]')
        assert override.rectangles == [{"x": 1, "y": 2, "width": 3, "height": 4}]
        assert override.skip_anonymization is False
        assert override.detections is None

    def test_rectangles_dict_form(self):
        override = AnonymizationOverride.from_json_string(
            '{"rectangles": [{"x": 1, "y": 2, "width": 3, "height": 4}]}')
        assert len(override.rectangles) == 1
        assert override.skip_anonymization is False

    def test_precomputed_detections_verbatim(self):
        """An 'objects' dict enters detections mode and survives verbatim —
        model_name, confidences and sub-threshold entries included."""
        payload = {
            "objects": [
                {"class_id": 0, "class_name": "person", "confidence": 0.91,
                 "scale": 1.0, "blur": 151,
                 "bbox": {"x1": 10, "y1": 20, "x2": 30, "y2": 60},
                 "blurred": True},
                {"class_id": 2, "class_name": "car", "confidence": 0.3,
                 "scale": 0.5, "blur": 101,
                 "bbox": {"x1": 5, "y1": 5, "x2": 9, "y2": 9},
                 "blurred": False},
            ],
            "model_name": "yolo-test",
        }
        override = AnonymizationOverride.from_json_string(json.dumps(payload))
        assert override.detections == payload
        # Precomputed mode must NOT read as skip — an old worker would have;
        # this is the compatibility hazard the upload flag help warns about.
        assert override.skip_anonymization is False
        assert override.rectangles == []

    def test_precomputed_empty_objects_is_not_skip(self):
        """'Checked, nothing found' is a detections-mode value (persisted
        verbatim for provenance), not the manual skip record."""
        override = AnonymizationOverride.from_json_string(
            '{"objects": [], "model_name": "yolo-test"}')
        assert override.detections == {"objects": [], "model_name": "yolo-test"}
        assert override.skip_anonymization is False

    def test_invalid_json_means_auto(self):
        assert AnonymizationOverride.from_json_string("{nope") is None


class TestParseExifDatetime:
    """Tests for parse_exif_datetime() — the captured_at parse.

    The upload metadata's captured_at (ms-ISO UTC from the Android fast-write
    path and the pics pipeline) lands in the same slot as embedded
    DateTimeOriginal, so this one function decides whether sub-second
    precision and UTC-ness survive.
    """

    def test_millisecond_iso_utc_parses_with_subseconds(self):
        from photo_processor import parse_exif_datetime
        dt = parse_exif_datetime("2026-08-09T11:10:07.996Z")
        assert dt is not None
        assert dt.microsecond == 996000
        assert dt.utcoffset().total_seconds() == 0

    def test_z_string_ignores_the_files_local_offset(self):
        # metadata captured_at overwrites DateTimeOriginal, but the file's
        # OffsetTimeOriginal (written by an EXIF-writing client, local time)
        # survives — applying it to an already-UTC value shifted the instant
        # by the timezone.
        from photo_processor import parse_exif_datetime
        dt = parse_exif_datetime("2026-08-09T11:10:07Z", "+02:00")
        assert dt is not None
        assert dt.hour == 11

    def test_naive_wall_clock_still_converts_via_offset(self):
        from photo_processor import parse_exif_datetime
        dt = parse_exif_datetime("2026:08:09 13:10:07", "+02:00")
        assert dt is not None
        assert dt.hour == 11
        assert dt.utcoffset().total_seconds() == 0

    def test_standard_exif_without_offset_assumed_utc(self):
        from photo_processor import parse_exif_datetime
        dt = parse_exif_datetime("2026:08:09 11:10:07")
        assert dt is not None
        assert dt.hour == 11
        assert dt.utcoffset().total_seconds() == 0


class TestSynthesizeProvenance:
    """What survives the upload-metadata hop into UserComment.

    This is a contract with the pics pipeline, not an implementation
    detail: a browser capture cannot write EXIF at all, and the Android
    fast-write path deliberately does not (the whole-file rewrite is the
    throughput cost it exists to avoid), so for both of them the metadata
    blob is the ONLY carrier of provenance.
    """

    def test_the_fast_write_stamp_survives_in_full(self):
        from photo_processor import synthesize_provenance
        out = json.loads(synthesize_provenance({
            "latitude": 50.1, "longitude": 14.4,     # not provenance, must not leak
            "location_source": "gps",
            "bearing_source": "android-compass-true",
            "location_age_ms": 207,
            "refined": True,
            "exposure": {"mode": "sports", "iso": 133, "outcome": "ontarget"},
        }))
        assert out["location_source"] == "gps"
        assert out["bearing_source"] == "android-compass-true"
        assert out["location_age_ms"] == 207
        assert out["refined"] is True
        # Nested, not stringified — a consumer reads exposure.mode directly.
        assert out["exposure"]["mode"] == "sports"
        # Geo lives in its own columns; duplicating it here would rot.
        assert "latitude" not in out

    def test_absent_keys_are_omitted_not_nulled(self):
        # An older client sends the two it knows; the rest must not appear
        # as nulls, which a consumer would have to special-case.
        from photo_processor import synthesize_provenance
        out = json.loads(synthesize_provenance({
            "location_source": "manual", "bearing_source": "arrow_drag",
        }))
        assert out == {"location_source": "manual", "bearing_source": "arrow_drag"}

    def test_nothing_to_say_means_no_usercomment(self):
        # None (not "{}"), so the caller leaves a genuinely embedded
        # UserComment alone rather than overwriting it with an empty object.
        from photo_processor import synthesize_provenance
        assert synthesize_provenance({"latitude": 50.1}) is None
        assert synthesize_provenance({}) is None
        assert synthesize_provenance(None) is None


class TestBrowserMetadataAcceptsProvenance:
    """The upload metadata model is a DOOR, and pydantic drops what it does
    not declare — silently.

    That is not hypothetical: the Android client sent location_age_ms and
    exposure, photo_processor was written to fold them into UserComment,
    and the worker never saw either, because BrowserMetadata did not list
    them. Nothing failed; the keys simply evaporated between the two.
    This test is the tripwire for the next such key.
    """

    @staticmethod
    def _browser_metadata():
        # Importing app touches UPLOAD_DIR at module scope, which is a
        # container path; point it at a temp dir so the model is reachable
        # from a host unit test.
        import sys, os, tempfile
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
        os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="hv-uploads-"))
        from app import BrowserMetadata
        return BrowserMetadata

    def test_the_fast_write_stamp_survives_validation(self):
        BrowserMetadata = self._browser_metadata()

        raw = json.dumps({
            "latitude": 50.1, "longitude": 14.4, "bearing": 13.2,
            "captured_at": "2026-08-12T10:43:13.084Z",
            "location_source": "gps",
            "bearing_source": "android-compass-true",
            "location_age_ms": 409,
            "refined": True,
            "exposure": {"mode": "sports", "iso": 133, "outcome": "ontarget"},
        })
        parsed = BrowserMetadata.model_validate_json(raw).model_dump(exclude_none=True)

        assert parsed["location_age_ms"] == 409
        assert parsed["refined"] is True
        assert parsed["exposure"]["mode"] == "sports"
        # …and the sub-second capture instant, which is what the whole
        # ms-ISO captured_at change exists for.
        assert parsed["captured_at"].endswith("10:43:13.084Z")

    def test_every_provenance_key_can_get_through(self):
        # Guards the two halves against drifting apart: photo_processor
        # copies PROVENANCE_KEYS out of the parsed metadata, so a key it
        # knows about that this model does not is dead on arrival.
        BrowserMetadata = self._browser_metadata()
        from photo_processor import PROVENANCE_KEYS

        declared = set(BrowserMetadata.model_fields)
        # 'v' is the pipeline's semantics version, sent by pics, not the app.
        missing = [k for k in PROVENANCE_KEYS if k not in declared and k != "v"]
        assert not missing, f"photo_processor reads {missing}, which BrowserMetadata drops"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
