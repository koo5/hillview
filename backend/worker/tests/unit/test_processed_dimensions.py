"""Exercise final photo dimensions through real decode/rendition generation.

Metadata extraction and publication are stubbed; pixels, probes, rotation and
WebP/DZI codecs are real. Each probe has an isolated auxiliary-worker policy.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest

WORKER = Path(__file__).resolve().parents[2]


def probe(case):
    import asyncio
    import json
    import tempfile
    from unittest.mock import patch

    import numpy as np
    from PIL import Image
    import pyvips

    import local_photos
    import photo_processor
    from photo_processor import PhotoProcessor

    with tempfile.TemporaryDirectory(prefix='processed-dimensions-') as directory:
        root = Path(directory)
        arch = root / 'arch'
        arch.mkdir()
        uploads = root / 'uploads'
        uploads.mkdir()
        processor = PhotoProcessor(str(uploads))
        processor.FULL_VARIANT_WIDTH = 8
        raw_size = (20, 12) if case == 'pyramid' else (21, 13) if case == 'cap' else (17, 9)
        source = root / ('input.jpg' if case == 'rotation' else 'input.png')
        if case == 'rotation':
            exif = Image.Exif()
            exif[274] = 6
            Image.new('RGB', raw_size, (30, 120, 190)).save(source, exif=exif)
        else:
            Image.new('RGB', raw_size, (30, 120, 190)).save(source)

        metadata = {'latitude': 50.0, 'longitude': 14.0, 'bearing': 45.0}
        if case not in ('cap', 'pyramid'):
            # Supplied orientation can disagree with the pixels (or agree in the
            # embedded-rotation control). This makes the preliminary probe swap.
            metadata['orientation_code'] = 6
        override = '[]'
        detections = {'objects': [{'class_id': 0, 'confidence': 0.3, 'blurred': False,
                                  'bbox': {'x1': 13, 'y1': 1, 'x2': 16, 'y2': 4}}]}
        if case == 'precomputed':
            override = json.dumps(detections)
        elif case == 'automatic':
            override = None

        dzi = None
        if case == 'pyramid':
            prefix = str(arch / 'pano')
            pyvips.Image.new_from_array(np.full((12, 20, 3), 120, dtype=np.uint8)).dzsave(
                prefix, tile_size=16, overlap=1, suffix='.webp[Q=97]')
            dzi = prefix + '.dzi'
        elif case == 'pyramid-mismatch':
            dzi = str(arch / 'wrong.dzi')
            Path(dzi).write_text('<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
                'TileSize="1024" Overlap="1" Format="webp"><Size Width="9" Height="17"/></Image>')

        publications = []

        async def publish(path, relative, *args, **kwargs):
            publications.append(path)
            return 'http://pics.test/' + relative

        async def detector(path, encoding=None):
            return photo_processor.read_image(path, encoding=encoding), detections

        extract = {'data': {}, 'gps': {}, 'debug': {}}
        with (patch.object(processor, 'extract_exif_data', return_value=extract),
              patch.object(processor, '_get_size_url', side_effect=publish),
              patch.object(processor, '_anonymize_image', side_effect=detector),
              patch.object(photo_processor, '_validate_input_path', side_effect=lambda path: path),
              patch.object(local_photos, 'EXTERNAL_DATA_DIR', str(root)),
              patch.dict(os.environ, {'LOCAL_PHOTO_URLS': 'arch=http://pics.test/arch'})):
            if case == 'pyramid':
                no_decode = patch.object(photo_processor, 'read_image', side_effect=AssertionError('decoded source on pyramid-only path'))
            else:
                from contextlib import nullcontext
                no_decode = nullcontext()
            with no_decode:
                operation = processor.process_uploaded_photo(str(source), source.name,
                    user_id='11111111-1111-4111-8111-111111111111', photo_id='probe',
                    metadata=metadata, anonymization_override=override, fast=True,
                    keep_pics_in_worker=True, local_pyramid_path=dzi)
                if case == 'pyramid-mismatch':
                    try:
                        asyncio.run(operation)
                    except ValueError as error:
                        assert 'pyramid' in str(error) and 'decoded' in str(error), str(error)
                    else:
                        raise AssertionError('accepted pyramid disagreed with decoded raster')
                    assert not publications, 'published before rejecting mismatched pyramid'
                    return
                result = asyncio.run(operation)

        expected = (9, 17) if case == 'rotation' else raw_size
        actual = result['width'], result['height']
        assert actual == expected, (case, actual, expected)
        full = result['sizes']['full']
        with Image.open(uploads / full['path']) as image:
            assert image.size == (full['width'], full['height'])
        assert full['width'] == processor.FULL_VARIANT_WIDTH < result['width']
        assert abs(full['height'] - expected[1] * full['width'] / expected[0]) < 1
        if case == 'pyramid':
            pyramid = full['pyramid']
            assert (pyramid['width'], pyramid['height']) == actual
        if case in ('precomputed', 'automatic'):
            assert result['detected_objects'] == detections


class ProcessedDimensionsTests(unittest.TestCase):
    def check_case(self, case):
        env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
               'HILLVIEW_AUX': '1'}
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--probe', case],
                                env=env, text=True, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-7000:])

    def test_metadata_orientation_uses_decoded_dimensions(self):
        self.check_case('skip')

    def test_full_rendition_cap_preserves_source_dimensions(self):
        self.check_case('cap')

    def test_embedded_rotation_is_reported_once(self):
        self.check_case('rotation')

    def test_precomputed_detections_keep_coordinates_and_decoded_dimensions(self):
        self.check_case('precomputed')

    def test_automatic_detections_use_decoded_dimensions(self):
        self.check_case('automatic')

    def test_pyramid_only_dimensions_do_not_require_decode(self):
        self.check_case('pyramid')

    def test_early_accepted_pyramid_must_match_decoded_raster(self):
        self.check_case('pyramid-mismatch')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--probe':
        probe(sys.argv[2])
    else:
        unittest.main()
