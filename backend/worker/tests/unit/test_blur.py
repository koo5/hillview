#!/usr/bin/env python3
"""
Unit tests for blur.py pure functions:
  - apply_blackout
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

# detections stub
detections_stub = types.ModuleType('detections')
detections_stub.TARGET_CLASSES = {0: 'person', 2: 'car'}
sys.modules['detections'] = detections_stub

# Remove any previously cached blur stub (e.g. installed by test_anonymize.py)
# so that the real blur.py module is imported here.
sys.modules.pop('blur', None)

from blur import apply_blackout  # noqa: E402


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
