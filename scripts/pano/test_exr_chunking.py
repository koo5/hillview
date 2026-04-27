#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["OpenEXR", "numpy", "pytest"]
# ///
"""Tests for the streaming chunked I/O in exr_meta.set_encoding and
exr_linearize.linearize.

The streaming logic chunks reads/writes by N scanlines (default 128) so
each writePixels buffer stays under the OpenEXR Python binding's 2 GB
signed-int size check. The chunk-boundary math is the part that's easy
to get subtly wrong (off-by-ones around the last partial chunk, dataWindow
y_min ≠ 0, single-chunk degenerate case), so the bulk of these tests
parametrize over heights that exercise each boundary regime with
SCANLINES_PER_CHUNK=4:

	height=3   single chunk, smaller than chunk size
	height=4   single chunk, exactly chunk size
	height=8   two full chunks, exact multiple
	height=17  four full + one partial chunk
	height=200 many chunks (50)

Bit-exact pixel preservation across set_encoding round-trips is verified
by writing a deterministic per-channel pattern, calling set_encoding
(which decompresses + recompresses every scanline), and reading back.

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
import Imath

import exr_meta
import exr_linearize


PT_HALF = Imath.PixelType(Imath.PixelType.HALF)
PT_FLOAT = Imath.PixelType(Imath.PixelType.FLOAT)


# --- helpers ---


def _dtype_for(pt):
	return np.float32 if pt == PT_FLOAT else np.float16


def make_test_exr(path, width, height, channels=("R", "G", "B", "A"),
									pixel_type=PT_FLOAT):
	"""Create an EXR with a deterministic per-channel pattern in [0, 1]
	that differs across channels (so a roundtrip mismatch on any single
	channel is detectable)."""
	header = OpenEXR.Header(width, height)
	header['channels'] = {c: Imath.Channel(pixel_type) for c in channels}

	dtype = _dtype_for(pixel_type)
	y_idx = np.arange(height)[:, None]
	x_idx = np.arange(width)[None, :]
	data = {}
	for ci, c in enumerate(channels):
		arr = ((ci * 113 + y_idx * width + x_idx) % 1024) / 1023.0
		data[c] = arr.astype(dtype).tobytes()

	out = OpenEXR.OutputFile(str(path), header)
	try:
		out.writePixels(data)
	finally:
		out.close()


def make_constant_exr(path, width, height, channels, pixel_type, value):
	"""Create an EXR filled with a single constant value across all channels."""
	header = OpenEXR.Header(width, height)
	header['channels'] = {c: Imath.Channel(pixel_type) for c in channels}
	dtype = _dtype_for(pixel_type)
	arr = np.full((height, width), value, dtype=dtype).tobytes()
	out = OpenEXR.OutputFile(str(path), header)
	try:
		out.writePixels({c: arr for c in channels})
	finally:
		out.close()


def read_exr_pixels(path):
	exr = OpenEXR.InputFile(str(path))
	try:
		header = exr.header()
		dw = header['dataWindow']
		width = dw.max.x - dw.min.x + 1
		height = dw.max.y - dw.min.y + 1
		channels = header['channels']
		data = {}
		for name, ch in channels.items():
			raw = exr.channel(name, ch.type)
			dtype = _dtype_for(ch.type)
			data[name] = np.frombuffer(raw, dtype=dtype).reshape((height, width))
		return data, header
	finally:
		exr.close()


# heights chosen to hit each chunk-boundary regime (with chunk=4)
CHUNK_BOUNDARY_HEIGHTS = [3, 4, 8, 17, 200]


# --- set_encoding ---


@pytest.mark.parametrize("height", CHUNK_BOUNDARY_HEIGHTS)
@pytest.mark.parametrize("pixel_type", [PT_FLOAT, PT_HALF])
def test_set_encoding_preserves_pixels(tmp_path, monkeypatch, height, pixel_type):
	monkeypatch.setattr(exr_meta, 'SCANLINES_PER_CHUNK', 4)
	src = tmp_path / "img.exr"
	make_test_exr(src, width=32, height=height, pixel_type=pixel_type)

	before, _ = read_exr_pixels(src)
	exr_meta.set_encoding(str(src), "linear")
	after, _ = read_exr_pixels(src)

	assert set(before) == set(after)
	for c in before:
		np.testing.assert_array_equal(
			before[c], after[c],
			err_msg=f"channel {c} mutated (h={height}, type={pixel_type})",
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
		power without clamp gives NaN. The clamp is the whole reason that
		np.maximum(v, 0.0) line exists."""
		out = exr_linearize.inv_srgb(np.array([-0.01, -1.0, -1e-9]))
		assert not np.any(np.isnan(out))
		assert np.all(out == 0.0)

	def test_returns_float32(self):
		# Output dtype matters for downstream tobytes() sizing.
		out = exr_linearize.inv_srgb(np.array([0.5], dtype=np.float64))
		assert out.dtype == np.float32


# --- linearize ---


@pytest.mark.parametrize("height", CHUNK_BOUNDARY_HEIGHTS)
def test_linearize_alpha_passes_through(tmp_path, monkeypatch, height):
	"""Alpha is a coverage mask, not light; linearize must NOT apply OETF
	to it (else compositing breaks)."""
	monkeypatch.setattr(exr_linearize, 'SCANLINES_PER_CHUNK', 4)
	src = tmp_path / "img.exr"
	out = tmp_path / "out.exr"
	make_test_exr(src, width=32, height=height,
								channels=("R", "G", "B", "A"), pixel_type=PT_FLOAT)
	before, _ = read_exr_pixels(src)
	exr_linearize.linearize(src, out)
	after, _ = read_exr_pixels(out)
	np.testing.assert_array_equal(before["A"], after["A"])


@pytest.mark.parametrize("height", CHUNK_BOUNDARY_HEIGHTS)
def test_linearize_applies_inv_srgb_to_rgb(tmp_path, monkeypatch, height):
	"""All RGB pixels = 0.5 → all output ≈ 0.21404 across every chunk."""
	monkeypatch.setattr(exr_linearize, 'SCANLINES_PER_CHUNK', 4)
	src = tmp_path / "img.exr"
	out = tmp_path / "out.exr"
	make_constant_exr(src, width=32, height=height,
										channels=("R", "G", "B"), pixel_type=PT_FLOAT, value=0.5)
	exr_linearize.linearize(src, out)
	after, _ = read_exr_pixels(out)
	for c in ("R", "G", "B"):
		assert after[c].shape == (height, 32), f"channel {c} wrong shape"
		assert after[c].mean() == pytest.approx(0.21404, abs=1e-4), \
			f"channel {c} not linearized correctly across {height} rows"
		# Every pixel should match — confirms no chunk boundary skipped or
		# duplicated rows
		np.testing.assert_allclose(after[c], 0.21404, atol=1e-4)


def test_linearize_preserves_storage_type(tmp_path, monkeypatch):
	"""HALF input → HALF output; FLOAT input → FLOAT output. Mixed in same
	file (e.g. half color + float depth) must be preserved per-channel."""
	monkeypatch.setattr(exr_linearize, 'SCANLINES_PER_CHUNK', 4)
	src = tmp_path / "img.exr"
	out = tmp_path / "out.exr"

	width, height = 8, 17
	header = OpenEXR.Header(width, height)
	header['channels'] = {
		'R': Imath.Channel(PT_HALF),
		'G': Imath.Channel(PT_HALF),
		'B': Imath.Channel(PT_HALF),
		'A': Imath.Channel(PT_FLOAT),
	}
	mid = np.full((height, width), 0.5, dtype=np.float16).tobytes()
	mid_f = np.full((height, width), 0.5, dtype=np.float32).tobytes()
	out_f = OpenEXR.OutputFile(str(src), header)
	try:
		out_f.writePixels({'R': mid, 'G': mid, 'B': mid, 'A': mid_f})
	finally:
		out_f.close()

	exr_linearize.linearize(src, out)

	after_exr = OpenEXR.InputFile(str(out))
	try:
		after_header = after_exr.header()
		assert after_header['channels']['R'].type == PT_HALF
		assert after_header['channels']['A'].type == PT_FLOAT
	finally:
		after_exr.close()


# --- chunk-count assertion ---
# These tests verify that the loop iterates the expected number of times,
# catching off-by-ones that wouldn't show up as data corruption (e.g.
# accidentally writing one chunk twice with the same data, or skipping
# the last partial chunk on an EXR whose height isn't a multiple of N).


def test_chunk_count_partial_last(tmp_path, monkeypatch):
	"""height=17 with chunk=4 should produce 4 full chunks + 1 partial = 5 calls."""
	monkeypatch.setattr(exr_meta, 'SCANLINES_PER_CHUNK', 4)
	src = tmp_path / "img.exr"
	make_test_exr(src, width=8, height=17, pixel_type=PT_FLOAT)

	# Spy on writePixels
	calls = []
	import OpenEXR as _oexr
	orig_open = _oexr.OutputFile

	class SpyOutputFile:
		def __init__(self, *a, **kw):
			self._inner = orig_open(*a, **kw)

		def writePixels(self, data, num=1):
			calls.append(num)
			return self._inner.writePixels(data, num)

		def close(self):
			return self._inner.close()

	monkeypatch.setattr(exr_meta.OpenEXR, 'OutputFile', SpyOutputFile)
	exr_meta.set_encoding(str(src), "linear")
	assert calls == [4, 4, 4, 4, 1], f"unexpected chunk sequence: {calls}"


if __name__ == "__main__":
	sys.exit(pytest.main([__file__, "-v"]))
