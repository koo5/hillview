"""Read pixels for size variants out of a DZI pyramid instead of decoding the
source image.

When an externally rendered pyramid (the pano pipeline's phase_13 output) is
accepted for a photo BEFORE the source is decoded, every size variant can be
derived from a pyramid level: the levels were box-shrunk by dzsave from the
lossless raster (no generation loss between levels — one WebP encode per
level is the only loss), and taking the smallest level at least 2x the target
then downscaling averages four pixels per output pixel, which decorrelates the
WebP artifacts of that one encode. Measured with scripts/pano/pyramid_bench.py:
a Q93 pyramid puts derived variants within ~0.3-0.8 dB of the decode path.

Everything here is BGR uint8, matching the worker's cv2 convention. Tiles are
decoded with cv2 (webp via libwebp), stitched with the DZI overlap cropped off
every interior edge, and only the tiles covering the requested region are
touched — a wide pano's crop variants need a few dozen tiles, not a level.
"""

import math
import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


def scale_bboxes(objects: List[Dict], factor: float) -> List[Dict]:
	"""Detections with their full-image bboxes rescaled by `factor` (identity at 1)."""
	if factor == 1:
		return objects
	return [{**o, 'bbox': {k: int(round(v * factor)) for k, v in o['bbox'].items()}} for o in objects]


class RasterSource:
	"""The decoded (and possibly anonymized) full raster as a variant source —
	the same interface as PyramidSource so consumers have one code path."""

	def __init__(self, image: np.ndarray, source_path: str, encoding: Optional[str]):
		self.image = image
		self.source_path = source_path
		self.encoding = encoding

	def for_width(self, target_w: int) -> np.ndarray:
		return self.image

	def for_center_crop(self, target_w: int, target_h: int) -> np.ndarray:
		return self.image

	def fresh_for_width(self, target_w: int) -> np.ndarray:
		"""Unblurred pixels, safe to mutate: the raster was anonymized in place,
		so this re-decodes the source."""
		from blur import read_image
		return read_image(self.source_path, encoding=self.encoding)


class PyramidSource:
	"""A validated DZI pyramid (descriptor already parsed by the caller)."""

	def __init__(self, dzi_path: str, meta: Dict):
		self.files_dir = dzi_path[:-len('.dzi')] + '_files'
		self.tile_size = int(meta['tile_size'])
		self.overlap = int(meta['overlap'])
		self.format = meta['format']
		self.width = int(meta['width'])
		self.height = int(meta['height'])
		# vips dzsave: level N = ceil(log2(max dim)); each level down halves
		# with ceil rounding (verified against a real phase_13 pyramid).
		self.max_level = math.ceil(math.log2(max(self.width, self.height)))
		self._level_cache: Dict[int, np.ndarray] = {}

	def level_dims(self, level: int) -> Tuple[int, int]:
		f = 2 ** (self.max_level - level)
		return math.ceil(self.width / f), math.ceil(self.height / f)

	def level_for(self, min_w: int, min_h: int = 0) -> int:
		"""Smallest level whose dims are >= (min_w, min_h); level 0-side clamp
		is the full-resolution level (nothing bigger exists)."""
		chosen = self.max_level
		for lv in range(self.max_level, -1, -1):
			lw, lh = self.level_dims(lv)
			if lw >= min_w and lh >= min_h:
				chosen = lv
			else:
				break
		return chosen

	def _tile(self, level: int, c: int, r: int) -> np.ndarray:
		path = os.path.join(self.files_dir, str(level), f"{c}_{r}.{self.format}")
		arr = cv2.imread(path, cv2.IMREAD_COLOR)
		if arr is None:
			raise ValueError(f"external pyramid tile unreadable: {path}")
		return arr

	def region(self, level: int, x0: int, y0: int, w: int, h: int) -> np.ndarray:
		"""Stitch level pixels [x0, x0+w) x [y0, y0+h) into one BGR array.

		DZI tile (c, r) covers level pixels [c*ts - o, (c+1)*ts + o) clamped
		to the level, so column c's array index for level x is x - c*ts + (o
		if c > 0 else 0); same for rows.
		"""
		lw, lh = self.level_dims(level)
		x0, y0 = max(0, x0), max(0, y0)
		w, h = min(w, lw - x0), min(h, lh - y0)
		out = np.empty((h, w, 3), dtype=np.uint8)
		ts, o = self.tile_size, self.overlap
		for c in range(x0 // ts, (x0 + w - 1) // ts + 1):
			for r in range(y0 // ts, (y0 + h - 1) // ts + 1):
				tile = self._tile(level, c, r)
				tx0, ty0 = c * ts, r * ts  # level coords of the tile's core origin
				ox = o if c > 0 else 0
				oy = o if r > 0 else 0
				# intersection of the tile core with the requested region, in level coords
				ix0, iy0 = max(x0, tx0), max(y0, ty0)
				ix1, iy1 = min(x0 + w, tx0 + ts), min(y0 + h, ty0 + ts)
				if ix1 <= ix0 or iy1 <= iy0:
					continue
				out[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0] = tile[oy + iy0 - ty0:oy + iy1 - ty0, ox + ix0 - tx0:ox + ix1 - tx0]
		return out

	def whole_level(self, level: int) -> np.ndarray:
		if level not in self._level_cache:
			lw, lh = self.level_dims(level)
			self._level_cache[level] = self.region(level, 0, 0, lw, lh)
		return self._level_cache[level]

	def for_width(self, target_w: int) -> np.ndarray:
		"""Whole level at least 2x `target_w` wide, cached — treat as read-only.

		NB when no level is that big (a target at or near full resolution) this
		clamps to the full-resolution level, so the caller re-encodes
		already-encoded tiles at ~1x — a second lossy generation the >=2x rule
		would otherwise have washed out. The worker therefore only uses this
		class as a variant source when the raster was never decoded AND the
		photo is >= 2x its largest for_width target (the guard in
		create_optimized_sizes), so the clamp is never hit from there.
		"""
		return self.whole_level(self.level_for(2 * target_w))

	def fresh_for_width(self, target_w: int) -> np.ndarray:
		"""Same level, as a private copy safe to mutate (e.g. blackout)."""
		return self.for_width(target_w).copy()

	def for_center_crop(self, target_w: int, target_h: int) -> np.ndarray:
		"""The center-crop source region for a (target_w x target_h) crop, at a
		level where that region is at least 2x the target in both axes.

		Mirrors create_center_crop's geometry (scale so the smaller dimension
		matches, then center-crop the other): in full-image coordinates the
		crop covers a centered box of (target_w/s, target_h/s) with
		s = max(target_w/W, target_h/H). Returned at level scale; feeding it
		to create_center_crop yields exactly the same output as feeding the
		full raster.
		"""
		s = max(target_w / self.width, target_h / self.height)
		box_w, box_h = target_w / s, target_h / s
		# smallest level where the box is still >= 2x the target
		level = self.max_level
		for lv in range(self.max_level, -1, -1):
			f = 2 ** (self.max_level - lv)
			if box_w / f >= 2 * target_w and box_h / f >= 2 * target_h:
				level = lv
			else:
				break
		f = 2 ** (self.max_level - level)
		lw, lh = self.level_dims(level)
		rw, rh = min(lw, math.ceil(box_w / f)), min(lh, math.ceil(box_h / f))
		return self.region(level, (lw - rw) // 2, (lh - rh) // 2, rw, rh)
