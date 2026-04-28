#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["OpenEXR", "numpy", "pytest"]
# ///
"""Tests for exr_meta.set_encoding and exr_linearize.linearize.

What's verified:

	- hillview:encoding round-trips: write the attribute, read it back,
		get the same string. This is the test that caught the original bug
		where the legacy InputFile/OutputFile API silently dropped custom
		string attributes — both scripts now use the modern OpenEXR.File
		API which serializes them as standard EXR string attributes.
	- Pixel data is bit-exact across a set_encoding round-trip (header
		change must not perturb pixels — even after PIZ decompress+recompress).
	- Channel storage types (HALF / FLOAT) are preserved.
	- inv_srgb math: known fixed points, low-branch boundary, negative
		clamp (the np.maximum guard against NaN from raising small negatives
		to 2.4 power, which enblend produces near edges).
	- linearize alpha pass-through (alpha is a coverage mask, not light).
	- linearize applies inv_srgb to RGB (constant fill round-trips through
		the known transfer-function value).
	- Mixed HALF + FLOAT channels in one image survive linearize.

Run:
	./test_exr_chunking.py
	# or
	pytest test_exr_chunking.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pytest

import OpenEXR

import exr_meta
import exr_linearize


# --- helpers ---


def make_test_exr(path, width, height, channels=("R", "G", "B", "A"),
									dtype=np.float32):
	"""Create an EXR with deterministic per-channel patterns in [0, 1].
	Different patterns per channel so a mismatch on any single channel is
	detectable."""
	y_idx = np.arange(height)[:, None]
	x_idx = np.arange(width)[None, :]
	chans = {}
	for ci, c in enumerate(channels):
		arr = ((ci * 113 + y_idx * width + x_idx) % 1024) / 1023.0
		chans[c] = arr.astype(dtype)
	header = {
		"compression": OpenEXR.ZIP_COMPRESSION,
		"type": OpenEXR.scanlineimage,
	}
	OpenEXR.File(header, chans).write(str(path))


def make_constant_exr(path, width, height, channels, dtype, value):
	"""Create an EXR filled with one constant value across all channels."""
	arr = np.full((height, width), value, dtype=dtype)
	chans = {c: arr.copy() for c in channels}
	header = {
		"compression": OpenEXR.ZIP_COMPRESSION,
		"type": OpenEXR.scanlineimage,
	}
	OpenEXR.File(header, chans).write(str(path))


def read_pixels(path):
	"""Return {channel_name: numpy_array} via the modern File API."""
	f = OpenEXR.File(str(path), separate_channels=True)
	return {name: ch.pixels for name, ch in f.channels().items()}


# A few heights that exercise different shapes (no chunking anymore, but
# size-dependent bugs still possible — height==1, height==prime, etc.).
TEST_HEIGHTS = [1, 4, 17, 200]


# --- set_encoding ---


@pytest.mark.parametrize("height", TEST_HEIGHTS)
@pytest.mark.parametrize("dtype", [np.float32, np.float16])
def test_set_encoding_preserves_pixels(tmp_path, height, dtype):
	"""set_encoding must not perturb pixel values, even though it
	decompresses+recompresses the whole file."""
	src = tmp_path / "img.exr"
	make_test_exr(src, width=32, height=height, dtype=dtype)

	before = read_pixels(src)
	exr_meta.set_encoding(str(src), "linear")
	after = read_pixels(src)

	assert set(before) == set(after)
	for c in before:
		assert before[c].dtype == after[c].dtype, \
			f"channel {c} dtype changed: {before[c].dtype} -> {after[c].dtype}"
		np.testing.assert_array_equal(
			before[c], after[c],
			err_msg=f"channel {c} mutated (h={height}, dtype={dtype.__name__})",
		)


@pytest.mark.parametrize("encoding", ["srgb", "linear"])
def test_set_encoding_attribute_round_trips(tmp_path, encoding):
	src = tmp_path / "img.exr"
	make_test_exr(src, width=8, height=4)
	exr_meta.set_encoding(str(src), encoding)
	assert exr_meta.read_encoding(str(src)) == encoding


def test_set_encoding_overwrites_existing_attribute(tmp_path):
	src = tmp_path / "img.exr"
	make_test_exr(src, width=8, height=4)
	exr_meta.set_encoding(str(src), "srgb")
	exr_meta.set_encoding(str(src), "linear")
	assert exr_meta.read_encoding(str(src)) == "linear"


def test_read_encoding_returns_none_for_untagged(tmp_path):
	"""read_encoding must report absence as None, not silently default —
	this is the contract the worker relies on to reject untagged files."""
	src = tmp_path / "img.exr"
	make_test_exr(src, width=8, height=4)
	assert exr_meta.read_encoding(str(src)) is None


def test_set_encoding_rejects_invalid(tmp_path):
	src = tmp_path / "img.exr"
	make_test_exr(src, width=8, height=4)
	with pytest.raises(ValueError, match="encoding must be one of"):
		exr_meta.set_encoding(str(src), "bogus")


def test_set_encoding_no_temp_file_on_success(tmp_path):
	"""Successful set should leave no .tmp turd."""
	src = tmp_path / "img.exr"
	make_test_exr(src, width=8, height=4)
	exr_meta.set_encoding(str(src), "linear")
	assert not (tmp_path / "img.exr.tmp").exists()


# --- inv_srgb ---


class TestInvSrgb:
	def test_zero(self):
		assert exr_linearize.inv_srgb(np.array([0.0]))[0] == pytest.approx(0.0)

	def test_one(self):
		# ((1 + 0.055) / 1.055)^2.4 = 1.0 exactly
		assert exr_linearize.inv_srgb(np.array([1.0]))[0] == pytest.approx(1.0, rel=1e-5)

	def test_midpoint(self):
		# ((0.5 + 0.055) / 1.055)^2.4 ≈ 0.21404
		assert exr_linearize.inv_srgb(np.array([0.5]))[0] == pytest.approx(0.21404, abs=1e-4)

	def test_low_branch_uses_linear(self):
		# 0.04 < 0.04045 threshold → uses linear segment v / 12.92
		assert exr_linearize.inv_srgb(np.array([0.04]))[0] == pytest.approx(0.04 / 12.92, abs=1e-6)

	def test_negative_clamped_no_nan(self):
		"""enblend produces slight negatives near edges; raising to 2.4
		power without clamp gives NaN. The np.maximum(v, 0.0) line exists
		precisely to suppress that."""
		out = exr_linearize.inv_srgb(np.array([-0.01, -1.0, -1e-9]))
		assert not np.any(np.isnan(out))
		assert np.all(out == 0.0)

	def test_returns_float32(self):
		# Output dtype matters for downstream tobytes()/storage sizing.
		out = exr_linearize.inv_srgb(np.array([0.5], dtype=np.float64))
		assert out.dtype == np.float32


# --- linearize ---


@pytest.mark.parametrize("height", TEST_HEIGHTS)
def test_linearize_drops_alpha_by_default(tmp_path, height):
	"""Default behavior: alpha is dropped from the output. Nothing
	downstream uses it and it skews the linearized EXR's vips min/max
	with enblend edge overshoots."""
	src = tmp_path / "img.exr"
	out = tmp_path / "out.exr"
	make_test_exr(src, width=32, height=height,
								channels=("R", "G", "B", "A"), dtype=np.float32)
	exr_linearize.linearize(src, out)
	after = read_pixels(out)
	assert "A" not in after, f"alpha should be dropped (h={height})"
	assert set(after) == {"R", "G", "B"}


@pytest.mark.parametrize("height", TEST_HEIGHTS)
def test_linearize_keep_alpha_passes_through(tmp_path, height):
	"""With keep_alpha=True, alpha survives unchanged — no OETF applied
	to it (else compositing breaks)."""
	src = tmp_path / "img.exr"
	out = tmp_path / "out.exr"
	make_test_exr(src, width=32, height=height,
								channels=("R", "G", "B", "A"), dtype=np.float32)
	before = read_pixels(src)
	exr_linearize.linearize(src, out, keep_alpha=True)
	after = read_pixels(out)
	assert "A" in after
	np.testing.assert_array_equal(before["A"], after["A"])


@pytest.mark.parametrize("height", TEST_HEIGHTS)
def test_linearize_applies_inv_srgb_to_rgb(tmp_path, height):
	"""All RGB pixels = 0.5 → all output ≈ 0.21404 across every row."""
	src = tmp_path / "img.exr"
	out = tmp_path / "out.exr"
	make_constant_exr(src, width=32, height=height,
										channels=("R", "G", "B"), dtype=np.float32, value=0.5)
	exr_linearize.linearize(src, out)
	after = read_pixels(out)
	for c in ("R", "G", "B"):
		assert after[c].shape == (height, 32), f"channel {c} wrong shape"
		np.testing.assert_allclose(after[c], 0.21404, atol=1e-4)


def test_linearize_preserves_storage_type(tmp_path):
	"""HALF input → HALF output; FLOAT input → FLOAT output. Mixed types
	in one file (e.g. half color + float depth) must be preserved
	per-channel. Tested with keep_alpha=True so the float A channel is
	visible in the output for the dtype check."""
	src = tmp_path / "img.exr"
	out = tmp_path / "out.exr"

	width, height = 8, 17
	chans = {
		'R': np.full((height, width), 0.5, dtype=np.float16),
		'G': np.full((height, width), 0.5, dtype=np.float16),
		'B': np.full((height, width), 0.5, dtype=np.float16),
		'A': np.full((height, width), 0.5, dtype=np.float32),
	}
	header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
	OpenEXR.File(header, chans).write(str(src))

	exr_linearize.linearize(src, out, keep_alpha=True)

	after = read_pixels(out)
	assert after['R'].dtype == np.float16
	assert after['G'].dtype == np.float16
	assert after['B'].dtype == np.float16
	assert after['A'].dtype == np.float32


# --- end-to-end pipeline integration ---


def test_linearize_then_set_encoding_roundtrip(tmp_path):
	"""The pipeline does linearize first, then exr_meta set --encoding linear
	(via subprocess). Verify we don't lose either pixel changes or the
	attribute when both run."""
	src = tmp_path / "img.exr"
	mid = tmp_path / "linearized.exr"
	make_constant_exr(src, width=16, height=8,
										channels=("R", "G", "B"), dtype=np.float32, value=0.5)
	exr_linearize.linearize(src, mid)
	exr_meta.set_encoding(str(mid), "linear")

	# Attribute persisted
	assert exr_meta.read_encoding(str(mid)) == "linear"
	# Pixels are linearized
	after = read_pixels(mid)
	for c in ("R", "G", "B"):
		np.testing.assert_allclose(after[c], 0.21404, atol=1e-4)


if __name__ == "__main__":
	sys.exit(pytest.main([__file__, "-v"]))
