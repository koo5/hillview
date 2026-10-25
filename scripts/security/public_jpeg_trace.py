#!/usr/bin/env python3
"""Bounded parser probes; run in a disposable worker image, not a service.

See docs/security/public-jpeg-review-2026-10-22.md for the Docker invocation.
Uses real production helpers and test-only tracing; no network or credentials
are needed. This is a finite compatibility/reachability corpus, not fuzzing.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

# Keep import-time/library chatter out of the machine-readable report.
sys.stdout = sys.stderr
os.environ['HILLVIEW_AUX'] = '0'
os.environ['YOLO_CONFIG_DIR'] = '/tmp/ultralytics'
from PIL import Image, ImageCms
import pyvips
import photo_processor
import blur

root = Path('/app/uploads/trace')
root.mkdir(parents=True, exist_ok=True)
profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
for name, mode, options in [
    ('baseline', 'RGB', {}), ('progressive', 'RGB', {'progressive': True}),
    ('grayscale', 'L', {}), ('cmyk', 'CMYK', {}),
    ('icc', 'RGB', {'icc_profile': profile}),
    ('orientation', 'RGB', {'exif': Image.Exif()}),
]:
    if name == 'orientation':
        options['exif'][274] = 6
    Image.new(mode, (31, 19)).save(root / (name + '.jpg'), **options)
base = (root / 'baseline.jpg').read_bytes()
(root / 'truncated.jpg').write_bytes(base[:len(base)//2])
(root / 'prefix-only.jpg').write_bytes(b'\xff\xd8\xff')
(root / 'trailing-data.jpg').write_bytes(base + b'HARMLESS_TRAILER')
Image.new('RGB', (31, 19)).save(root / 'disguised.jpg', format='PNG')
# Malformed ICC contents exercise rejection without an exploit payload.
Image.new('RGB', (31, 19)).save(root / 'bad-icc.jpg', icc_profile=b'not an ICC profile')

real_run = subprocess.run
real_call = pyvips.Operation.call
real_open = Image.open
reports = []
for path in sorted(root.glob('*.jpg')):
    report = {'fixture': path.name, 'calls': [], 'results': {}}
    trace = root / (path.stem + '.perl-trace')
    os.environ['HILLVIEW_TRACE_FILE'] = str(trace)
    def run(cmd, *args, **kwargs):
        report['calls'].append({'subprocess': cmd})
        assert cmd[0] == 'exiftool', cmd
        result = real_run(cmd, *args, **kwargs)
        report['calls'].append({'returncode': result.returncode, 'stderr': result.stderr})
        return result
    def call(name, *args, **kwargs):
        report['calls'].append({'vips': name})
        assert not any(x in name.lower() for x in ('magick', 'tiffload', 'openexrload'))
        return real_call(name, *args, **kwargs)
    def image_open(*args, **kwargs):
        report['calls'].append({'pillow_formats': kwargs.get('formats')})
        assert kwargs.get('formats') == ['JPEG']
        return real_open(*args, **kwargs)
    processor = photo_processor.PhotoProcessor()
    orientation = 6 if path.stem == 'orientation' else 1
    operations = {
        'metadata': lambda: processor.extract_exif_data(str(path))['debug'],
        'dimensions': lambda: processor.get_image_dimensions(str(path), orientation),
        'pixels': lambda: list(blur.read_image(str(path)).shape),
    }
    with patch.object(subprocess, 'run', run), patch.object(pyvips.Operation, 'call', call), patch.object(Image, 'open', image_open):
        for name, operation in operations.items():
            try:
                report['results'][name] = {'ok': operation()}
            except Exception as error:
                report['results'][name] = {'error': type(error).__name__, 'message': str(error)}
        # This helper relies on admission by its caller. Exercise it only when
        # the complete pixel decode succeeded, as in the production pipeline.
        if 'ok' in report['results']['pixels']:
            output = root / (path.stem + '.webp')
            Image.new('RGB', (31, 19)).save(output, format='WEBP')
            photo_processor.copy_exif_data(str(path), str(output))
    report['exiftool_trace'] = trace.read_text().splitlines() if trace.exists() else []
    reports.append(report)
# Exercise the actual variant branches. Replace only artifact publication and
# detector work; the auto-mode stub still calls the real read_image helper.
async def publish(path, relative, *args, **kwargs):
    return 'test://' + relative
async def detector(path, encoding=None):
    return blur.read_image(path, encoding=encoding), {'objects': []}
for mode, override in [('auto', None), ('skip', '[]'),
                       ('manual', '[{"x":1,"y":1,"width":5,"height":5}]'),
                       ('precomputed', '{"objects":[]}')]:
    for fast in (False, True):
        report = {'fixture': f'mode-{mode}-fast-{fast}', 'calls': [], 'results': {}}
        trace = root / (report['fixture'] + '.perl-trace')
        os.environ['HILLVIEW_TRACE_FILE'] = str(trace)
        processor = photo_processor.PhotoProcessor()
        with patch.object(subprocess, 'run', run), patch.object(pyvips.Operation, 'call', call), patch.object(Image, 'open', image_open), patch.object(processor, '_get_size_url', publish), patch.object(processor, '_anonymize_image', detector):
            sizes, detections = asyncio.run(processor.create_optimized_sizes(
                str(root / 'baseline.jpg'), '11111111-1111-4111-8111-111111111111/probe',
                31, 19, anonymization_override=photo_processor.AnonymizationOverride.from_json_string(override),
                fast=fast, output_base=str(root / report['fixture']),
                local_pyramid_path='/does-not-exist.dzi'))
            report['results']['variants'] = list(map(str, sizes))
        report['exiftool_trace'] = trace.read_text().splitlines() if trace.exists() else []
        reports.append(report)
# Turn policy violations into a failing command, even when production helpers
# catch an exception. Compatibility errors for malformed fixtures remain data.
for report in reports:
    assert not any(v.get('error') == 'AssertionError' for v in report['results'].values() if isinstance(v, dict)), report
    for event in report['calls']:
        assert event.get('subprocess', ['exiftool'])[0] == 'exiftool', event
        if 'vips' in event:
            assert not any(x in event['vips'].lower() for x in ('magick', 'tiffload', 'openexrload')), event
for report in reports:
    if report['fixture'] in ('baseline.jpg', 'progressive.jpg', 'grayscale.jpg', 'cmyk.jpg', 'icc.jpg', 'orientation.jpg'):
        dimensions = report['results']['dimensions']['ok']
        pixels = report['results']['pixels']['ok']
        assert tuple(dimensions) == (pixels[1], pixels[0]), report
print(json.dumps(reports, indent=2), file=sys.__stdout__)
