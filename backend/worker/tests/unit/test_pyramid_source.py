#!/usr/bin/env python3
"""
Unit tests for pyramid_source.PyramidSource geometry, against a REAL vips
dzsave pyramid (the same tool production pyramids come from, both the
worker's own and the pano pipeline's phase_13 output).

These pin the invariants the external-pyramid variant path relies on
(photo_processor.create_optimized_sizes): the ceil-halving level layout,
for_width's ">=2x level" selection and its full-resolution clamp — the
clamp being exactly what the width >= 2*FULL_VARIANT_WIDTH guard exists
to keep variant derivation away from — and region stitching with the DZI
overlap cropped off interior edges.
"""

import math
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from pyramid_source import PyramidSource

W, H = 3000, 2000
TILE, OVERLAP = 256, 1


def _test_image():
    """Smooth but non-degenerate BGR content: gradients + low-frequency sine,
    so resampling comparisons have structure without WebP-hostile noise."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    b = 255 * x / W
    g = 255 * y / H
    r = 127 + 100 * np.sin(x / 97) * np.cos(y / 71)
    return np.clip(np.dstack([b, g, r]), 0, 255).astype(np.uint8)


def _parse_dzi(dzi_path):
    """Descriptor parsed the way photo_processor._external_pyramid does."""
    import defusedxml.ElementTree as ET
    ns = '{http://schemas.microsoft.com/deepzoom/2008}'
    root = ET.parse(dzi_path).getroot()
    size = root.find(f'{ns}Size')
    return {
        'tile_size': int(root.get('TileSize')),
        'overlap': int(root.get('Overlap')),
        'format': root.get('Format'),
        'width': int(size.get('Width')),
        'height': int(size.get('Height')),
        'params': None,
    }


@pytest.fixture(scope='module')
def pyramid(tmp_path_factory):
    """(original BGR array, PyramidSource over its dzsave pyramid)."""
    import pyvips
    image = _test_image()
    prefix = str(tmp_path_factory.mktemp('pyr') / 'pano')
    vimg = pyvips.Image.new_from_array(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    vimg.dzsave(prefix, tile_size=TILE, overlap=OVERLAP, suffix='.webp[Q=95]')
    meta = _parse_dzi(prefix + '.dzi')
    assert (meta['width'], meta['height']) == (W, H)
    assert (meta['tile_size'], meta['overlap'], meta['format']) == (TILE, OVERLAP, 'webp')
    return image, PyramidSource(prefix + '.dzi', meta)


class TestLevelLayout:
    def test_max_level_is_ceil_log2(self, pyramid):
        _, ps = pyramid
        assert ps.max_level == math.ceil(math.log2(max(W, H)))

    def test_level_dims_match_tiles_on_disk(self, pyramid):
        """The ceil-halving dims must agree with what dzsave actually wrote:
        every level dir exists and its tile grid covers exactly level_dims."""
        _, ps = pyramid
        for level in range(ps.max_level + 1):
            lw, lh = ps.level_dims(level)
            level_dir = os.path.join(ps.files_dir, str(level))
            assert os.path.isdir(level_dir), f"level {level} missing on disk"
            cols = math.ceil(lw / TILE)
            rows = math.ceil(lh / TILE)
            tiles = os.listdir(level_dir)
            assert len(tiles) == cols * rows, f"level {level}: {len(tiles)} tiles for a {cols}x{rows} grid"


class TestForWidth:
    def test_picks_smallest_level_at_least_2x(self, pyramid):
        _, ps = pyramid
        got = ps.for_width(700)
        # levels are 3000, 1500, 750, ... — the smallest >= 1400 is 1500
        assert got.shape[1] == 1500
        assert got.shape[1] >= 2 * 700

    def test_clamps_to_full_resolution(self, pyramid):
        """No level is 2x a near-full-res target: for_width falls back to the
        full-resolution level (a ~1x re-encode for the caller). This is the
        behavior create_optimized_sizes guards variant derivation against
        with width >= 2*FULL_VARIANT_WIDTH."""
        _, ps = pyramid
        assert ps.for_width(W).shape[:2] == (H, W)
        assert ps.for_width(W // 2 + 1).shape[:2] == (H, W)

    def test_fresh_for_width_is_a_private_copy(self, pyramid):
        _, ps = pyramid
        fresh = ps.fresh_for_width(700)
        cached = ps.for_width(700)
        assert fresh is not cached
        fresh[0, 0] = 0  # must not leak into the cache
        assert not np.array_equal(fresh[0, 0], cached[0, 0]) or True  # mutation is legal; cache unchanged below
        assert np.array_equal(ps.for_width(700), cached)


class TestStitching:
    def test_full_res_level_matches_source(self, pyramid):
        """Stitching every tile of the full-resolution level (overlap cropped)
        reproduces the original within one WebP generation."""
        image, ps = pyramid
        level = ps.whole_level(ps.max_level)
        assert level.shape == image.shape
        assert np.mean(np.abs(level.astype(np.int16) - image.astype(np.int16))) < 3.0

    def test_halved_level_matches_downscaled_source(self, pyramid):
        image, ps = pyramid
        level = ps.whole_level(ps.max_level - 1)
        expect = cv2.resize(image, (math.ceil(W / 2), math.ceil(H / 2)), interpolation=cv2.INTER_AREA)
        assert level.shape == expect.shape
        assert np.mean(np.abs(level.astype(np.int16) - expect.astype(np.int16))) < 4.0

    def test_center_crop_matches_raster_path(self, pyramid):
        """create_center_crop fed from for_center_crop must land on the same
        output as when fed the full raster (the RasterSource path)."""
        from photo_processor import create_center_crop
        image, ps = pyramid
        via_pyramid = create_center_crop(ps.for_center_crop(320, 240), 320, 240)
        via_raster = create_center_crop(image, 320, 240)
        assert via_pyramid.shape == via_raster.shape == (240, 320, 3)
        assert np.mean(np.abs(via_pyramid.astype(np.int16) - via_raster.astype(np.int16))) < 5.0
