#!/usr/bin/env python3
"""Trace extraction/copy of upstream metadata fixtures in an isolated image.

Mount pinned upstream t/images at /fixtures. These are metadata test files,
not necessarily decodable photographs; this is not an upload acceptance test.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from PIL import Image

root = Path('/tmp/metadata-corpus')
root.mkdir()
files = []
for path in sorted(Path('/fixtures').iterdir()):
    if path.is_file() and path.read_bytes()[:3] == b'\xff\xd8\xff':
        local = root / (path.stem + '.jpg')
        local.write_bytes(path.read_bytes())
        files.append((path.name, local))
Image.new('RGB', (31, 19)).save(root / 'baseline.jpg')
video = Path('/fixtures/QuickTime.mov').read_bytes()
# The source QuickTime fixture is also tested directly as a positive control.
(root / 'video.mov').write_bytes(video)
(root / 'video-trailer.jpg').write_bytes((root / 'baseline.jpg').read_bytes() + video)
files += [('synthetic-video-trailer', root / 'video-trailer.jpg'),
          ('quicktime-positive-control', root / 'video.mov')]

def run(command, trace):
    env = {**os.environ, 'HILLVIEW_TRACE_FILE': str(trace)}
    proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
    return proc

rows = []
for name, source in files:
    row = {'fixture': name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    for mode, extra in [('extract', []), ('extract_ee_control', ['-ee'])]:
        if mode != 'extract' and name not in ('synthetic-video-trailer', 'quicktime-positive-control'):
            continue
        trace = root / f'{source.name}.{mode}.trace'
        proc = run(['exiftool', '-json', '-n', *extra, str(source)], trace)
        row[mode] = {'returncode': proc.returncode, 'stderr': proc.stderr,
                     'metadata': json.loads(proc.stdout)[0] if proc.stdout.strip().startswith('[') else None,
                     'trace': sorted(set(trace.read_text().splitlines())) if trace.exists() else []}
    if source.suffix == '.jpg':
        output = root / (source.stem + '.webp')
        Image.new('RGB', (31, 19)).save(output, format='WEBP')
        trace = root / f'{source.name}.copy.trace'
        proc = run(['exiftool', '-overwrite_original', '-TagsFromFile', str(source),
                    '-all:all', '-EXIF:Orientation=', str(output)], trace)
        row['copy'] = {'returncode': proc.returncode, 'stderr': proc.stderr,
                       'trace': sorted(set(trace.read_text().splitlines())) if trace.exists() else []}
        # Read back tags from the generated artifact too: successful copying
        # alone does not establish preservation of metadata values.
        readback = run(['exiftool', '-json', '-n', str(output)], root / f'{source.name}.readback.trace')
        row['copy']['readback_returncode'] = readback.returncode
        row['copy']['metadata'] = json.loads(readback.stdout)[0] if readback.stdout.strip().startswith('[') else None
    rows.append(row)
print(json.dumps(rows, indent=2))
