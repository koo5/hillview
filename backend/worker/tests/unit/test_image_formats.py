"""Exercise format policy in fresh workers, including disguised inputs."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

WORKER = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('enabled', ['0', '1'])
@pytest.mark.parametrize('name,header,internal,bmp', [
    ('photo.jpg', b'\xff\xd8\xff', False, False),
    ('renamed.jpg', b'\x89PNG\r\n\x1a\n', True, False),
    ('renamed.jpg', b'GIF89a', True, False),
    ('renamed.jpg', b'RIFF\x00\x00\x00\x00WEBP', True, False),
    ('input.png', b'\xff\xd8\xff', True, False),
    ('photo.png', b'\x89PNG\r\n\x1a\n', True, False),
    ('photo.gif', b'GIF89a', True, False),
    ('photo.webp', b'RIFF\x00\x00\x00\x00WEBP', True, False),
    ('renamed.jpg', b'\x76\x2f\x31\x01', True, False),
    ('renamed.jpg', b'II*\x00', True, False),
    ('renamed.jpg', b'MM\x00+', True, False),
    ('input.cr2', b'II*\x00', True, False),
    ('input.exr', b'\xff\xd8\xff', True, False),
    ('renamed.jpg', b'BM', False, True),
    ('input.bmp', b'\xff\xd8\xff', False, True),
])
def test_policy_before_native_parser(tmp_path, enabled, name, header, internal, bmp):
    path = tmp_path / name
    path.write_bytes(header)
    rejected = bmp or (internal and enabled == '0')
    script = '''
import sys
from unittest.mock import patch
import pyvips
from image_formats import require_supported_image
from blur import read_image
with patch.object(pyvips.Image, 'new_from_file', side_effect=AssertionError('decoder reached')):
    if sys.argv[2] == 'reject':
        for operation in (require_supported_image, read_image):
            try:
                operation(sys.argv[1])
            except ValueError:
                pass
            else:
                raise AssertionError('input was accepted')
    else:
        require_supported_image(sys.argv[1])
'''
    env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
           'HILLVIEW_AUX': enabled}
    subprocess.run([sys.executable, '-c', script, str(path), 'reject' if rejected else 'allow'],
                   env=env, check=True, timeout=20)


def test_internal_exr_uses_libvips(tmp_path):
    # Real library encode/decode; the public worker must block the same input.
    script = '''
import sys
import numpy as np
import OpenEXR
import pyvips
from blur import read_image
path = sys.argv[1]
with OpenEXR.File({}, {'RGB': np.full((5, 7, 3), 0.5, dtype=np.float32)}) as output:
    output.write(path)
image = read_image(path, encoding='srgb')
assert image.shape == (5, 7, 3)
assert np.all(np.abs(image.astype(int) - 128) <= 1)
'''
    env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
           'HILLVIEW_AUX': '1'}
    subprocess.run([sys.executable, '-c', script, str(tmp_path / 'photo.exr')],
                   env=env, check=True, timeout=20)


@pytest.mark.parametrize('header', [b'\x76\x2f\x31\x01', b'II*\x00', b'\x89PNG\r\n\x1a\n', b'GIF89a', b'RIFF\x00\x00\x00\x00WEBP'])
def test_public_metadata_and_dimensions_reject_before_parsing(tmp_path, header):
    path = tmp_path / 'renamed.jpg'
    path.write_bytes(header)
    script = '''
import sys
from unittest.mock import patch
from photo_processor import PhotoProcessor
processor = PhotoProcessor()
with patch('photo_processor._validate_input_path', side_effect=lambda path: path):
    with patch('photo_processor.subprocess.run', side_effect=AssertionError('metadata parser reached')):
        for operation in (processor.extract_exif_data, lambda path: processor.get_image_dimensions(path, 1)):
            try:
                operation(sys.argv[1])
            except ValueError as error:
                assert 'HILLVIEW_AUX' in str(error)
            else:
                raise AssertionError('internal input was accepted')
'''
    env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
           'HILLVIEW_AUX': '0'}
    subprocess.run([sys.executable, '-c', script, str(path)], env=env, check=True, timeout=20)


def test_public_jpeg_and_external_pyramid_policy(tmp_path):
    script = """
import sys
from unittest.mock import patch
from PIL import Image
import pyvips
import photo_processor
from blur import read_image
from pyramid_source import PyramidSource
path = sys.argv[1]
Image.new('RGB', (7, 5), (90, 130, 170)).save(path, format='JPEG')
# The public path must not use a generic decoder or accept offered tile input.
with patch.object(pyvips.Image, 'new_from_file', side_effect=AssertionError('generic loader')):
    assert read_image(path).shape == (5, 7, 3)
processor = photo_processor.PhotoProcessor()
with patch.object(photo_processor, '_validate_input_path', side_effect=lambda path: path), patch.object(photo_processor.subprocess, 'check_output', side_effect=AssertionError('identify reached')):
    assert processor.get_image_dimensions(path, 1) == (7, 5)
    assert processor.get_image_dimensions(path, 6) == (5, 7)
with patch('defusedxml.ElementTree.parse', side_effect=AssertionError('external XML parsed')):
    assert processor._external_pyramid('/does-not-exist.dzi', 7, 5, False, False, None, 'test') is None
try:
    PyramidSource('/does-not-exist.dzi', {})
except ValueError as error:
    assert 'HILLVIEW_AUX' in str(error)
else:
    raise AssertionError('external tiles accepted')
"""
    env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common'}
    env.pop('HILLVIEW_AUX', None)  # Default is public, even if the obsolete flag is set.
    env['ALLOW_PANORAMA_FORMATS'] = '1'
    subprocess.run([sys.executable, '-c', script, str(tmp_path / 'photo.jpg')],
                   env=env, check=True, timeout=20)


def test_auxiliary_probe_preserves_identify_command(tmp_path):
    script = """
import sys
from unittest.mock import patch
from PIL import Image
import photo_processor
path = sys.argv[1]
Image.new('RGB', (7, 5)).save(path, format='PNG')
processor = photo_processor.PhotoProcessor()
with patch.object(photo_processor, '_validate_input_path', side_effect=lambda path: path), patch.object(photo_processor.subprocess, 'check_output', return_value=b'7 5') as identify, patch.object(photo_processor.Image, 'open', side_effect=AssertionError('Pillow auxiliary probe')):
    assert processor.get_image_dimensions(path, 6) == (5, 7)
    identify.assert_called_once_with(['identify', '-ping', '-format', '%w %h', path], timeout=photo_processor.IMAGE_TOOL_TIMEOUT)
"""
    env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
           'HILLVIEW_AUX': '1'}
    subprocess.run([sys.executable, '-c', script, str(tmp_path / 'photo.png')],
                   env=env, check=True, timeout=20)


def test_policy_import_does_not_change_global_vips_loaders():
    script = """
from unittest.mock import patch
import pyvips
with patch.object(pyvips, 'operation_block_set', side_effect=AssertionError('global loader mutation')):
    import image_formats
"""
    for enabled in ('0', '1'):
        env = {**os.environ, 'PYTHONPATH': str(WORKER), 'HILLVIEW_AUX': enabled}
        subprocess.run([sys.executable, '-c', script], env=env, check=True, timeout=20)


# (aux, allow_bodies, name, header, local_source, accepted)
SOURCE_CASES = [
    # Aux worker, default: a body must be public JPEG; a local path may be anything supported.
    ('1', None, 'photo.jpg', b'\xff\xd8\xff', False, True),
    ('1', None, 'pano.exr', b'\x76\x2f\x31\x01', False, False),
    ('1', None, 'renamed.jpg', b'\x76\x2f\x31\x01', False, False),
    ('1', None, 'scan.tiff', b'II*\x00', False, False),
    ('1', None, 'photo.png', b'\x89PNG\r\n\x1a\n', False, False),
    # JPEG magic is not enough for a body: the suffix picks dcraw/identify readers.
    ('1', None, 'input.cr2', b'\xff\xd8\xff', False, False),
    ('1', None, 'input.exr', b'\xff\xd8\xff', False, False),
    ('1', None, 'pano.exr', b'\x76\x2f\x31\x01', True, True),
    ('1', None, 'scan.tiff', b'II*\x00', True, True),
    ('1', None, 'input.cr2', b'II*\x00', True, True),
    # The opt-out restores the old aux behaviour for bodies.
    ('1', '1', 'pano.exr', b'\x76\x2f\x31\x01', False, True),
    ('1', '0', 'pano.exr', b'\x76\x2f\x31\x01', False, False),
    # A local path never bypasses the process-wide policy, nor does the opt-out.
    ('0', None, 'pano.exr', b'\x76\x2f\x31\x01', True, False),
    ('0', '1', 'pano.exr', b'\x76\x2f\x31\x01', False, False),
    ('0', None, 'photo.jpg', b'\xff\xd8\xff', False, True),
    # BMP stays refused everywhere.
    ('1', '1', 'renamed.jpg', b'BM', True, False),
]


@pytest.mark.parametrize('aux,allow_bodies,name,header,local_source,accepted', SOURCE_CASES)
def test_source_policy(tmp_path, aux, allow_bodies, name, header, local_source, accepted):
    path = tmp_path / name
    path.write_bytes(header)
    script = '''
import sys
from image_formats import require_supported_source
local_source = sys.argv[2] == 'local'
try:
    require_supported_source(sys.argv[1], local_source=local_source)
except ValueError:
    accepted = False
else:
    accepted = True
assert accepted == (sys.argv[3] == 'accept'), f'accepted={accepted}'
'''
    env = {**os.environ, 'PYTHONPATH': str(WORKER), 'HILLVIEW_AUX': aux}
    env.pop('ALLOW_AUX_FORMATS_IN_UPLOADS', None)
    if allow_bodies is not None:
        env['ALLOW_AUX_FORMATS_IN_UPLOADS'] = allow_bodies
    subprocess.run([sys.executable, '-c', script, str(path),
                    'local' if local_source else 'body', 'accept' if accepted else 'reject'],
                   env=env, check=True, timeout=20)


def test_aux_upload_body_rejected_before_any_parser(tmp_path):
    # The job entry point, not just the policy function: an EXR body on an aux
    # worker must fail before exiftool, dcraw or any decoder runs, and a caller
    # that does not say where the file came from must get the closed default.
    path = tmp_path / 'pano.exr'
    path.write_bytes(b'\x76\x2f\x31\x01' + b'\x00' * 64)
    script = '''
import asyncio, sys
from unittest.mock import patch
import pyvips
import photo_processor
processor = photo_processor.PhotoProcessor()
blocked = AssertionError('parser reached')
with patch.object(photo_processor.subprocess, 'run', side_effect=blocked), \\
     patch.object(photo_processor.subprocess, 'check_output', side_effect=blocked), \\
     patch.object(pyvips.Image, 'new_from_file', side_effect=blocked), \\
     patch.object(processor, 'extract_exif_data', side_effect=blocked):
    for kwargs in ({}, {'local_source': False}):
        try:
            asyncio.run(processor.process_uploaded_photo(sys.argv[1], 'pano.exr',
                user_id='11111111-1111-4111-8111-111111111111', photo_id='probe', **kwargs))
        except ValueError as error:
            assert 'local_photo_path' in str(error), str(error)
        else:
            raise AssertionError(f'EXR body accepted with {kwargs}')
'''
    env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
           'HILLVIEW_AUX': '1'}
    env.pop('ALLOW_AUX_FORMATS_IN_UPLOADS', None)
    subprocess.run([sys.executable, '-c', script, str(path)], env=env, check=True, timeout=30)


def test_job_runner_forwards_local_source():
    # app.process -> worker_processing -> process_uploaded_photo: the flag must
    # survive the pool hop, or every local EXR would be refused as a body.
    script = '''
from unittest.mock import patch
import photo_processor
import worker_processing
seen = []
async def fake(**kwargs):
    seen.append(kwargs.get('local_source'))
    return {}
with patch.object(photo_processor.photo_processor, 'process_uploaded_photo', side_effect=fake):
    for flag in (True, False):
        worker_processing._run_photo_processing('/x.exr', 'x.exr', 'u', 'p', None, local_source=flag)
    worker_processing._run_photo_processing('/x.jpg', 'x.jpg', 'u', 'p', None)
assert seen == [True, False, False], seen
'''
    env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
           'HILLVIEW_AUX': '1'}
    subprocess.run([sys.executable, '-c', script], env=env, check=True, timeout=30)
