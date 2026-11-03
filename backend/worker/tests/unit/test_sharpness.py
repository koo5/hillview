#!/usr/bin/env python3
"""
Unit tests for sharpness.py on synthetic images with known blur: defocus
lowers the isotropic score, a one-directional smear shows up in the
directional terms, anonymization boxes are masked, wide sources are skipped.
"""

import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import sharpness


def _texture(h=768, w=1024, seed=0):
	"""Isotropic multi-scale texture in 0..1 — a stand-in for foliage or gravel."""
	rng = np.random.default_rng(seed)
	img = np.zeros((h, w), np.float32)
	for sigma, weight in ((0.7, 1.0), (2.0, 0.8), (6.0, 0.6)):
		img += weight * cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), sigma)
	img -= img.min()
	return img / img.max()


def _motion(img, length=15, horizontal=True):
	k = np.zeros((length, length), np.float32)
	if horizontal:
		k[length // 2, :] = 1
	else:
		k[:, length // 2] = 1
	return cv2.filter2D(img, -1, k / length)


def _noisy(img, seed=1, amount=0.01):
	"""Sensor-like noise added after the blur, as in a real camera."""
	return np.clip(img + amount * np.random.default_rng(seed).standard_normal(img.shape).astype(np.float32), 0, 1)


def test_defocus_lowers_isotropic_score():
	sharp = _texture()
	soft = cv2.GaussianBlur(sharp, (0, 0), 2.5)
	a, b = sharpness.measure_grey(sharp), sharpness.measure_grey(soft)
	assert b["rel_p50"] < 0.5 * a["rel_p50"]
	assert b["rel_p90"] < 0.5 * a["rel_p90"]


@pytest.mark.parametrize("horizontal, direction", [(True, "0"), (False, "90")])
def test_motion_blur_has_a_consistent_weak_direction(horizontal, direction):
	sharp = sharpness.measure_grey(_noisy(_texture()))
	smeared = sharpness.measure_grey(_noisy(_motion(_texture(), horizontal=horizontal)))
	assert smeared["weak_direction"] == direction
	assert smeared["weak_direction_agreement"] > 0.8
	# an isotropic texture has no preferred weak direction
	assert sharp["weak_direction_agreement"] < 0.6
	assert smeared["weak_rel_p50"] < 0.5 * sharp["weak_rel_p50"]


def test_flat_image_uses_no_tiles():
	doc = sharpness.measure_grey(np.full((512, 512), 0.5, np.float32))
	assert doc["tiles_total"] == 64
	assert doc["tiles_used"] == 0
	assert "rel_p50" not in doc


def test_too_small_for_one_tile():
	doc = sharpness.measure_grey(np.zeros((32, 32), np.float32))
	assert doc["tiles_total"] == 0 and doc["tiles_used"] == 0


def _doodle(img, x1, y1, x2, y2):
	"""What the worker paints over a detection: a flat fill plus crisp line art."""
	out = img.copy()
	out[y1:y2, x1:x2] = 0.3
	cv2.rectangle(out, (x1 + 10, y1 + 10), (x2 - 10, y2 - 10), 1.0, 3)
	cv2.line(out, (x1 + 10, y1 + 10), (x2 - 10, y2 - 10), 1.0, 3)
	return out


def test_anonymization_box_is_masked():
	"""A soft photo with a crisp doodle reads sharp unless the box is masked."""
	soft = cv2.GaussianBlur(_texture(), (0, 0), 3.0)
	box = (300, 200, 700, 600)
	painted = _doodle(soft, *box)
	unmasked = sharpness.measure_grey(painted)
	h, w = painted.shape
	masked = sharpness.measure_grey(painted, sharpness.box_mask((h, w), [box], 1.0, 1.0))
	baseline = sharpness.measure_grey(soft)
	assert unmasked["rel_max"] > 2 * baseline["rel_max"]
	assert masked["rel_max"] == pytest.approx(baseline["rel_max"], rel=0.05)
	assert masked["tiles_used"] < baseline["tiles_used"]
	assert 0.15 < masked["masked_fraction"] < 0.35


def test_box_mask_scales_and_pads():
	# source frame 2000×1000, working frame 1000×500: the box halves, then grows
	mask = sharpness.box_mask((500, 1000), [(400, 200, 600, 400)], 0.5, 0.5)
	ys, xs = np.nonzero(mask)
	assert xs.min() == 190 and xs.max() == 309      # 200..300, padded by 10% of 100 = 10
	assert ys.min() == 90 and ys.max() == 209


def test_measure_bytes_roundtrip_maps_boxes_from_source_frame():
	img = (np.dstack([_texture(600, 800)] * 3) * 255).astype(np.uint8)
	ok, buf = cv2.imencode(".png", img)
	assert ok
	# boxes given in a source frame twice the stored size
	doc = sharpness.measure_bytes(buf.tobytes(), 800, 600, boxes=[(0, 0, 800, 600)], source_size=(1600, 1200))
	assert doc["work_width"] == 800 and doc["work_height"] == 600
	assert doc["scale_from_source"] == 0.5
	assert 0.25 < doc["masked_fraction"] < 0.4


def test_load_work_image_caps_area():
	img = np.zeros((3000, 4000, 3), np.uint8)
	ok, buf = cv2.imencode(".png", img)
	assert ok
	work = sharpness.load_work_image(buf.tobytes(), 4000, 3000)
	assert abs(work.width * work.height - sharpness.WORK_AREA) / sharpness.WORK_AREA < 0.01
	small = sharpness.load_work_image(cv2.imencode(".png", img[:300, :400])[1].tobytes(), 400, 300)
	assert (small.width, small.height) == (400, 300)   # never enlarged
