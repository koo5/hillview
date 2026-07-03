#!/usr/bin/env python3
"""
Unit tests for blur.apply_blur — with REAL cv2 (test_blur.py stubs cv2 to
exercise pure-numpy helpers, which leaves apply_blur untested). apply_blur
is what both the auto path (anonymize.py) and the precomputed-detections
override (photo_processor.py) paint with: it must repaint the bbox region
and leave the rest of the frame alone.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Undo the module stubs other unit files may have installed earlier in the
# session (test_anonymize/test_blur stub cv2/detections/blur); this file
# needs the real modules. Later-collected stubbers re-install their own.
for _mod in ('cv2', 'detections', 'blur'):
	sys.modules.pop(_mod, None)

from blur import apply_blur  # noqa: E402


def _image(w=200, h=120):
	"""A noisy BGR frame — any flat repaint is a large, certain diff."""
	rng = np.random.default_rng(0)
	return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


def _obj(x1, y1, x2, y2, cls_id):
	"""A detection in the stored detected_objects shape (manual and machine
	rects alike carry class_id + bbox; that's all apply_blur reads)."""
	return {
		'class_id': cls_id,
		'bbox': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
		'blur': 500,
		'blurred': True,
	}


class TestApplyBlur:

	def test_truck_region_repainted(self):
		image = _image()
		before = image.copy()
		apply_blur('/seed/path.jpg', image, [_obj(40, 20, 160, 100, 7)])
		region_before = before[20:100, 40:160].astype(int)
		region_after = image[20:100, 40:160].astype(int)
		assert np.abs(region_after - region_before).max() > 50, \
			"bbox region was not visibly repainted"

	def test_pixels_outside_region_untouched(self):
		image = _image()
		before = image.copy()
		apply_blur('/seed/path.jpg', image, [_obj(40, 20, 160, 100, 7)])
		# 5px margin: the stick-figure stroke thickness may kiss the bbox edge.
		assert np.array_equal(image[:15, :], before[:15, :])
		assert np.array_equal(image[105:, :], before[105:, :])
		assert np.array_equal(image[:, :35], before[:, :35])
		assert np.array_equal(image[:, 165:], before[:, 165:])

	def test_unknown_class_paints_block_without_icon(self):
		"""class_id None (manual override rects) resolves to no draw function —
		a plain color block, and must not raise."""
		image = _image()
		before = image.copy()
		apply_blur('/seed/path.jpg', image, [_obj(10, 10, 60, 60, None)])
		assert not np.array_equal(image[10:60, 10:60], before[10:60, 10:60])

	def test_empty_detections_noop(self):
		image = _image()
		before = image.copy()
		apply_blur('/seed/path.jpg', image, [])
		assert np.array_equal(image, before)

	def test_out_of_bounds_bbox_clamped(self):
		"""Coords beyond the frame are clamped, not an exception (bbox comes
		from stored/foreign data in the precomputed path)."""
		image = _image(60, 40)
		before = image.copy()
		apply_blur('/seed/path.jpg', image, [_obj(-10, -10, 500, 500, 2)])
		assert not np.array_equal(image, before)

	def test_zero_area_after_clamp_skipped(self):
		"""A bbox entirely outside the frame yields an empty ROI — skipped."""
		image = _image(60, 40)
		before = image.copy()
		apply_blur('/seed/path.jpg', image, [_obj(500, 500, 600, 600, 2)])
		assert np.array_equal(image, before)


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
