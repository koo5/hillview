#!/usr/bin/env python3
"""
Unit tests for the external-pyramid variant-source decision in
photo_processor.create_optimized_sizes, run in-process on the dev path
(keep_pics_in_worker=True, fast=True, skip-anonymization override — the
pano pipeline's actual upload shape).

The decision under test: an accepted external pyramid is the VARIANT
source only when the photo is >= 2*FULL_VARIANT_WIDTH wide, so every
for_width target has a >=2x level (no near-1x re-encode of WebP tiles);
below that the pyramid is accepted for SERVING only and the source is
decoded for the variants. Decode taken/skipped is proven, not inferred:
read_image is monkeypatched to either count calls or raise.
"""

import asyncio
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

import local_photos
import photo_processor
from photo_processor import AnonymizationOverride, PhotoProcessor

SKIP = AnonymizationOverride(rectangles=[])  # "[]": skip anonymization — blur-free provable pre-decode


def _gradient(width, height):
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    return np.clip(np.dstack([255 * x / width, 255 * y / height, np.full_like(x, 96)]), 0, 255).astype(np.uint8)


def _write_dzi(path, width, height, tile_size=1024, overlap=1, fmt='webp'):
    """A descriptor WITHOUT tiles: any attempt to derive pixels from this
    pyramid raises in PyramidSource._tile, so a test that passes proves the
    raster was the source."""
    with open(path, 'w') as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
                f'TileSize="{tile_size}" Overlap="{overlap}" Format="{fmt}">'
                f'<Size Width="{width}" Height="{height}"/></Image>')


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Dev-serve environment: an 'arch' root under a fake EXTERNAL_DATA_DIR
    (where offered pyramids live), URLs for it and for the worker's own
    uploads volume, and a PhotoProcessor over a tmp uploads dir."""
    arch = tmp_path / 'arch'
    arch.mkdir()
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    monkeypatch.setattr(local_photos, 'EXTERNAL_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('LOCAL_PHOTO_URLS', 'arch=http://pics.test/arch')
    monkeypatch.setenv('WORKER_PICS_URL', 'http://pics.test/w')
    return arch, PhotoProcessor(upload_dir=str(uploads))


def _process(proc, source_path, width, height, dzi_path):
    return asyncio.run(proc.create_optimized_sizes(
        str(source_path), '42/p1', width, height, photo_id='p1',
        anonymization_override=SKIP, fast=True,
        keep_pics_in_worker=True, local_pyramid_path=str(dzi_path)))


def test_wide_enough_photo_derives_from_pyramid_without_decoding(env, tmp_path, monkeypatch):
    """width == 2*FULL_VARIANT_WIDTH (the guard's boundary): every variant
    comes from pyramid levels and the source is NEVER decoded — read_image
    raising proves it. The pyramid here is real (dzsave), because its tiles
    are actually read."""
    import pyvips
    arch, proc = env
    width, height = 2 * PhotoProcessor.FULL_VARIANT_WIDTH, 512
    image = _gradient(width, height)
    prefix = str(arch / 'pano')
    pyvips.Image.new_from_array(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).dzsave(
        prefix, tile_size=1024, overlap=1, suffix='.webp[Q=93]')

    def _no_decode(*a, **kw):
        raise AssertionError('source was decoded on the skip-decode path')
    monkeypatch.setattr(photo_processor, 'read_image', _no_decode)

    source = tmp_path / 'src.jpg'  # never opened as pixels
    source.write_bytes(b'not an image')
    sizes_info, detections = _process(proc, source, width, height, prefix + '.dzi')

    assert detections == {'objects': [], 'manual': True}
    assert sizes_info['full']['width'] == PhotoProcessor.FULL_VARIANT_WIDTH
    for size in (320, 1200, 2048):
        assert size in sizes_info
    pyramid = sizes_info['full']['pyramid']
    assert pyramid['external'] is True
    assert pyramid['dzi_url'] == 'http://pics.test/arch/pano.dzi'
    assert (pyramid['width'], pyramid['height']) == (width, height)


def test_narrower_photo_decodes_and_keeps_pyramid_for_serving_only(env, tmp_path, monkeypatch):
    """Accepted pyramid on a photo below 2*FULL_VARIANT_WIDTH: the 'full'
    variant would be a near-1x re-encode of tiles, so the source is decoded
    and the raster is the variant source (tiles are absent — deriving from
    the pyramid would raise). The pyramid is still published for serving."""
    arch, proc = env
    width, height = 12000, 400
    source = tmp_path / 'src.png'
    assert cv2.imwrite(str(source), _gradient(width, height))
    dzi = arch / 'pano.dzi'
    _write_dzi(dzi, width, height)

    real_read_image = photo_processor.read_image
    calls = []

    def _counting(*a, **kw):
        calls.append(a)
        return real_read_image(*a, **kw)
    monkeypatch.setattr(photo_processor, 'read_image', _counting)

    sizes_info, _ = _process(proc, source, width, height, dzi)

    assert len(calls) == 1
    assert sizes_info['full']['width'] == PhotoProcessor.FULL_VARIANT_WIDTH
    pyramid = sizes_info['full']['pyramid']
    assert pyramid['external'] is True
    assert pyramid['dzi_url'] == 'http://pics.test/arch/pano.dzi'


def test_unreadable_descriptor_declines_offer_and_processes_normally(env, tmp_path):
    """A garbage .dzi is a DECLINED offer, not a failed photo: processing
    proceeds from the decoded raster and no pyramid is published (fast mode
    renders no own pyramid either)."""
    arch, proc = env
    width, height = 640, 480
    source = tmp_path / 'src.png'
    assert cv2.imwrite(str(source), _gradient(width, height))
    dzi = arch / 'bad.dzi'
    dzi.write_text('this is not a DZI descriptor')

    sizes_info, _ = _process(proc, source, width, height, dzi)

    assert sizes_info['full']['width'] == width
    assert 'pyramid' not in sizes_info['full']
    assert 320 in sizes_info
