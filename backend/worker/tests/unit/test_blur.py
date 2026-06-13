#!/usr/bin/env python3
"""
Unit tests for blur.py pure functions:
  - apply_blackout
  - normalize_to_srgb EXR encoding precedence (supplied > header tag > reject)
"""

import sys
import os
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# cv2 stub — apply_blackout only uses numpy slice-assign; no actual cv2 calls.
# Install before importing blur so the module-level `import cv2` succeeds.
cv2_stub = types.ModuleType('cv2')
sys.modules['cv2'] = cv2_stub

# detections stub — installed via direct assignment, so it must be complete:
# it overwrites any stub from earlier-collected modules and persists for the
# rest of the session (e.g. when test_photo_processor imports photo_processor,
# which does `from detections import should_blur`).
detections_stub = types.ModuleType('detections')
detections_stub.TARGET_CLASSES = {0: 'person', 2: 'car'}
detections_stub.DETECT_CONFIDENCE = 0.25
detections_stub.BLUR_CONFIDENCE = 0.4
detections_stub.should_blur = lambda o: o.get('confidence') is None or o['confidence'] >= 0.4
sys.modules['detections'] = detections_stub

# Remove any previously cached blur stub (e.g. installed by test_anonymize.py)
# so that the real blur.py module is imported here.
sys.modules.pop('blur', None)

import blur  # noqa: E402
from blur import apply_blackout, normalize_to_srgb  # noqa: E402


def _make_image(h=100, w=100, fill=255):
    """Return a white BGR image."""
    return np.full((h, w, 3), fill, dtype=np.uint8)


def _det(x1, y1, x2, y2, cls_id=0):
    return {'bbox': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}, 'class_id': cls_id}


class TestApplyBlackout:
    def test_single_region_blacked_out(self):
        image = _make_image()
        apply_blackout(image, [_det(10, 10, 40, 40)])
        assert np.all(image[10:40, 10:40] == 0)

    def test_pixels_outside_region_unchanged(self):
        image = _make_image()
        apply_blackout(image, [_det(10, 10, 40, 40)])
        # top-left corner should be untouched
        assert np.all(image[0:10, 0:10] == 255)
        assert np.all(image[40:, 40:] == 255)

    def test_multiple_regions(self):
        image = _make_image()
        apply_blackout(image, [_det(0, 0, 20, 20), _det(50, 50, 80, 80)])
        assert np.all(image[0:20, 0:20] == 0)
        assert np.all(image[50:80, 50:80] == 0)
        # untouched area between the two boxes
        assert np.all(image[25:45, 25:45] == 255)

    def test_empty_detections(self):
        image = _make_image()
        apply_blackout(image, [])
        assert np.all(image == 255)

    def test_out_of_bounds_clipped(self):
        """Coords outside the image dimensions must be clamped, not raise."""
        image = _make_image(50, 50)
        apply_blackout(image, [_det(-10, -10, 200, 200)])
        # The whole image should be zeroed (clamped to [0,50]×[0,50])
        assert np.all(image == 0)

    def test_zero_area_detection_ignored(self):
        """A box where x1==x2 or y1==y2 has no area; image must be unchanged."""
        image = _make_image()
        apply_blackout(image, [_det(20, 20, 20, 50)])  # x1 == x2
        assert np.all(image == 255)
        apply_blackout(image, [_det(20, 20, 50, 20)])  # y1 == y2
        assert np.all(image == 255)

    def test_inverted_coords_ignored(self):
        """x2 < x1 or y2 < y1 — clamp yields x2<=x1, so no pixels written."""
        image = _make_image()
        apply_blackout(image, [_det(80, 80, 10, 10)])
        assert np.all(image == 255)

    def test_full_image_blackout(self):
        image = _make_image(100, 100)
        apply_blackout(image, [_det(0, 0, 100, 100)])
        assert np.all(image == 0)

    def test_returns_none(self):
        """apply_blackout modifies in place and returns None."""
        image = _make_image()
        result = apply_blackout(image, [_det(10, 10, 50, 50)])
        assert result is None

    def test_image_modified_in_place(self):
        """apply_blackout must operate on the passed array, not a copy."""
        image = _make_image()
        original_id = id(image)
        apply_blackout(image, [_det(10, 10, 50, 50)])
        assert id(image) == original_id
        assert np.all(image[10:50, 10:50] == 0)


class _FakeVips:
    """Minimal stand-in for a pyvips image exercising only the methods
    normalize_to_srgb touches on a clean float EXR (no ICC, no ushort path).

    Records every interpretation passed to .copy() so tests can assert which
    EXR-encoding branch ran: 'linear' → scrgb, 'srgb' → srgb.
    """

    def __init__(self, fmt='float', bands=3):
        self.format = fmt
        self.bands = bands
        self.interpretation = 'scrgb'
        self.copied_interpretations = []

    def __getitem__(self, _sl):
        return self

    def copy(self, interpretation=None):
        if interpretation is not None:
            self.interpretation = interpretation
            self.copied_interpretations.append(interpretation)
        return self

    def get_typeof(self, _name):
        return 0  # no icc-profile-data

    def colourspace(self, space):
        self.interpretation = space
        return self

    def __mul__(self, _other):
        return self

    def cast(self, fmt):
        self.format = fmt
        return self


class TestNormalizeToSrgbEncoding:
    """EXR encoding source precedence: supplied encoding > header tag > reject."""

    def test_supplied_encoding_preferred_over_header(self, monkeypatch):
        """A caller-supplied encoding wins and the header is never read."""
        def _boom(_path):
            raise AssertionError("_exr_encoding must not be called when encoding is supplied")
        monkeypatch.setattr(blur, '_exr_encoding', _boom)

        img = _FakeVips()
        normalize_to_srgb(img, source_path='/tmp/pano.exr', encoding='srgb')
        assert img.copied_interpretations == ['srgb']

    def test_supplied_linear_marks_scrgb(self, monkeypatch):
        monkeypatch.setattr(blur, '_exr_encoding', lambda _p: (_ for _ in ()).throw(AssertionError("header read")))
        img = _FakeVips()
        normalize_to_srgb(img, source_path='/tmp/pano.exr', encoding='linear')
        assert img.copied_interpretations == ['scrgb']

    def test_falls_back_to_header_tag(self, monkeypatch):
        """With no supplied encoding, the embedded header tag is honored."""
        monkeypatch.setattr(blur, '_exr_encoding', lambda _p: 'linear')
        img = _FakeVips()
        normalize_to_srgb(img, source_path='/tmp/pano.exr', encoding=None)
        assert img.copied_interpretations == ['scrgb']

    def test_rejects_when_neither_supplied_nor_tagged(self, monkeypatch):
        """Untagged EXR with no supplied encoding is still rejected outright."""
        monkeypatch.setattr(blur, '_exr_encoding', lambda _p: None)
        img = _FakeVips()
        with pytest.raises(ValueError, match='hillview:encoding'):
            normalize_to_srgb(img, source_path='/tmp/pano.exr', encoding=None)

    def test_rejects_unknown_supplied_encoding(self, monkeypatch):
        monkeypatch.setattr(blur, '_exr_encoding', lambda _p: None)
        img = _FakeVips()
        with pytest.raises(ValueError, match='unknown hillview:encoding'):
            normalize_to_srgb(img, source_path='/tmp/pano.exr', encoding='bogus')
