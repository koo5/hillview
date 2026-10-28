#!/usr/bin/env python3
"""Read-only audit of Photo dimensions against full and ordinary renditions.

Exact swaps and swapped aspect ratios are separate from ordinary downscaling.
Metadata is evidence, not proof of the image header dimensions. Optional anomaly
JSONL includes image URLs for a subsequent header check; keep it private.
"""

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory_detections import bbox_issues, month


def dimensions(width, height):
	return (width, height) if all(type(v) is int and v > 0 for v in (width, height)) else None


def same_aspect(a, b):
	# Allow roughly a pixel of integer rounding in a resized rendition.
	return abs(a[0] * b[1] - a[1] * b[0]) <= max(*a, *b) * 1.5


def classify(photo, full):
	if photo is None:
		return 'missing-or-invalid-photo-dimensions'
	if full is None:
		return 'missing-or-invalid-full-dimensions'
	if photo == full:
		return 'exact-match'
	if photo == full[::-1]:
		return 'exact-width-height-reversal'
	if same_aspect(photo, full):
		return 'normal-full-downscale' if full[0] <= photo[0] + 1 else 'same-aspect-full-larger'
	if same_aspect(photo[::-1], full):
		return 'reversed-aspect-full-downscale' if full[0] <= photo[1] + 1 else 'reversed-aspect-full-larger'
	return 'other-aspect-mismatch'


def is_suspect(kind):
	return kind not in ('exact-match', 'normal-full-downscale', 'missing-or-invalid-full-dimensions')


class Audit:
	def __init__(self):
		self.counts = Counter()
		self.groups = defaultdict(lambda: defaultdict(Counter))
		self.bounds = Counter()
		self.examples = defaultdict(list)

	def add(self, row):
		sizes = row['sizes']
		full = (sizes.get('full') or {}) if isinstance(sizes, dict) else {}
		if not isinstance(full, dict):
			full = {}
		photo_dims = dimensions(row['width'], row['height'])
		full_dims = dimensions(full.get('width'), full.get('height'))
		kind = classify(photo_dims, full_dims)
		self.counts[kind] += 1
		for group, value in (
			('processed_month', month(row['processed_at'])), ('processing_status', row['processing_status']),
			('deleted', row['deleted']), ('orientation', row['orientation']),
			('processed_by_worker', row['processed_by_worker']),
		):
			self.groups[group][str(value)][kind] += 1
		detected = row['detected_objects']
		objects = detected.get('objects') if isinstance(detected, dict) else []
		if not isinstance(objects, list):
			objects = []
		photo_exceeds = full_exceeds = reversed_exceeds = 0
		for obj in objects:
			if not isinstance(obj, dict):
				continue
			if photo_dims:
				photo_exceeds += 'bbox-exceeds-image' in bbox_issues(obj, *photo_dims)
				reversed_exceeds += 'bbox-exceeds-image' in bbox_issues(obj, *photo_dims[::-1])
			if full_dims:
				full_exceeds += 'bbox-exceeds-image' in bbox_issues(obj, *full_dims)
		self.bounds['objects_exceeding_photo_row'] += photo_exceeds
		self.bounds['photos_with_objects_exceeding_photo_row'] += bool(photo_exceeds)
		if kind == 'exact-width-height-reversal':
			self.bounds['reversed_photos_with_detections'] += bool(objects)
			self.bounds['objects_exceeding_full_on_exact_reversal'] += full_exceeds
			self.bounds['photo_bound_errors_resolved_by_reversal'] += photo_exceeds - reversed_exceeds
		ordinary = []
		if isinstance(sizes, dict):
			for name, value in sizes.items():
				if not str(name).isdigit() or not isinstance(value, dict):
					continue
				dims = dimensions(value.get('width'), value.get('height'))
				if dims:
					ordinary.append({'name': str(name), 'dimensions': dims, 'url': value.get('url')})
		agree_full = sum(full_dims is not None and same_aspect(v['dimensions'], full_dims) for v in ordinary)
		agree_photo = sum(photo_dims is not None and same_aspect(v['dimensions'], photo_dims) for v in ordinary)
		ordinary_disagrees_full = full_dims is not None and agree_full < len(ordinary)
		small_320 = next((v['dimensions'] for v in ordinary if v['name'] == '320'), None)
		legacy_selection = bool(small_320 and full_dims and small_320[0] > small_320[1] and full_dims[0] < full_dims[1])
		self.bounds['photos_with_ordinary_aspect_disagreeing_full'] += ordinary_disagrees_full
		self.bounds['legacy_fix_sizes_selection'] += legacy_selection
		entry = {
			'id': row['id'], 'classification': kind, 'photo_dimensions': photo_dims,
			'full_dimensions': full_dims, 'full_url': full.get('url'),
			'processed_at': row['processed_at'], 'orientation': row['orientation'],
			'processing_status': row['processing_status'], 'deleted': row['deleted'],
			'detections': len(objects), 'boxes_exceeding_photo': photo_exceeds,
			'boxes_exceeding_full': full_exceeds,
			'ordinary_renditions': ordinary, 'ordinary_aspects_agree_full': agree_full,
			'ordinary_aspects_agree_photo': agree_photo,
			'ordinary_aspect_disagrees_full': ordinary_disagrees_full,
			'legacy_fix_sizes_selection': legacy_selection,
		}
		if len(self.examples[kind]) < 8:
			self.examples[kind].append({k: v for k, v in entry.items() if k not in ('ordinary_renditions', 'full_url')})
		return entry

	def report(self):
		return {'photos_scanned': sum(self.counts.values()), 'classifications': dict(self.counts),
		        'bbox_checks': dict(self.bounds), 'examples': dict(self.examples),
		        'groups': {group: dict(values) for group, values in self.groups.items()}}


async def scan(url, anomaly_output):
	import asyncpg

	conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://', 1),
	                             server_settings={'default_transaction_read_only': 'on',
	                                              'application_name': 'photo-dimensions-audit'})
	audit = Audit()
	try:
		await conn.set_type_codec('json', schema='pg_catalog', encoder=json.dumps, decoder=json.loads)
		async with conn.transaction(isolation='repeatable_read', readonly=True):
			metadata = dict(await conn.fetchrow('''SELECT current_database() AS database,
			    current_timestamp AS snapshot_at, current_setting('transaction_read_only') AS read_only'''))
			async for row in conn.cursor('''
			    SELECT id, width, height, sizes, detected_objects, processed_at, processing_status,
			           processed_by_worker, deleted, exif_data->'data'->>'Orientation' AS orientation
			    FROM public.photos ORDER BY id''', prefetch=500):
				entry = audit.add(dict(row))
				if is_suspect(entry['classification']) or entry['ordinary_aspect_disagrees_full']:
					anomaly_output.write(json.dumps(entry, default=str) + '\n')
		return {'snapshot': metadata, **audit.report()}
	finally:
		await conn.close()


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--database-url-env', required=True)
	parser.add_argument('--source', required=True)
	parser.add_argument('--output', required=True, type=Path)
	parser.add_argument('--anomalies-output', required=True, type=Path)
	args = parser.parse_args()
	url = os.environ.get(args.database_url_env)
	if not url:
		parser.error('Specified DB URL environment variable is empty')
	args.anomalies_output.parent.mkdir(parents=True, exist_ok=True)
	fd = os.open(args.anomalies_output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	with os.fdopen(fd, 'w') as stream:
		report = asyncio.run(scan(url, stream))
	report.update(source=args.source, generated_at=datetime.now(timezone.utc).isoformat())
	args.output.parent.mkdir(parents=True, exist_ok=True)
	args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + '\n')
	print(json.dumps({k: report[k] for k in ('photos_scanned', 'classifications', 'bbox_checks')}, indent=2))


if __name__ == '__main__':
	main()
