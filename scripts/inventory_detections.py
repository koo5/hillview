#!/usr/bin/env python3
"""Read-only inventory of photos.detected_objects; never imports app/test setup.

Run with backend/.venv/bin/python. Supply --database-url-env DATABASE_URL or
--input rows.jsonl (one decoded photo row per line), and an explicit --source
label. The database scan uses one repeatable-read, read-only snapshot, including
deleted and unfinished photos. Output contains counts and bounded issue IDs,
not the detections themselves. No dotenv loading or default database target.
"""

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from common.detections import BLUR_CONFIDENCE, is_blurred  # noqa: E402


PHOTO_SQL = """
SELECT id, captured_at, uploaded_at, processed_at, width, height,
       processing_status, deleted, detected_objects,
       detected_objects IS NULL AS detections_sql_null
FROM public.photos ORDER BY id
"""


def finite_number(value):
	return type(value) in (int, float) and math.isfinite(value)


def utc_datetime(value):
	if value is None:
		return None
	if isinstance(value, str):
		value = datetime.fromisoformat(value.replace('Z', '+00:00'))
	if value.tzinfo is None:
		value = value.replace(tzinfo=timezone.utc)
	return value.astimezone(timezone.utc)


def month(value):
	value = utc_datetime(value)
	return value.strftime('%Y-%m') if value is not None else None


def object_format(obj):
	if not isinstance(obj, dict):
		return 'invalid-object'
	if 'blurred' in obj:
		return 'explicit' if type(obj['blurred']) is bool else 'invalid-blurred'
	if obj.get('confidence') is None:
		return 'legacy-no-confidence'
	if not finite_number(obj['confidence']) or not 0 <= obj['confidence'] <= 1:
		return 'invalid-confidence'
	return 'legacy-confidence'


def bbox_issues(obj, width, height):
	box = obj.get('bbox')
	if not isinstance(box, dict) or any(
		not finite_number(box.get(k)) for k in ('x1', 'y1', 'x2', 'y2')
	):
		return ['bbox-malformed']
	x1, y1, x2, y2 = (box[k] for k in ('x1', 'y1', 'x2', 'y2'))
	issues = []
	if any(type(box[k]) is not int for k in ('x1', 'y1', 'x2', 'y2')):
		issues.append('bbox-non-integer')
	if x2 <= x1 or y2 <= y1:
		issues.append('bbox-empty-or-reversed')
	if min(x1, y1, x2, y2) < 0:
		issues.append('bbox-negative')
	if not all(finite_number(v) and v > 0 for v in (width, height)):
		issues.append('bbox-bounds-unknown')
	elif max(x1, x2) > width or max(y1, y2) > height:
		issues.append('bbox-exceeds-image')
	return issues


class Inventory:
	def __init__(self, example_limit=10):
		self.example_limit = example_limit
		self.photos = Counter()
		self.formats = Counter()
		self.photo_formats = Counter()
		self.verdicts = Counter()
		self.format_verdicts = defaultdict(Counter)
		self.processed_ranges = {}
		self.issues = Counter()
		self.issue_photos = Counter()
		self.issue_formats = defaultdict(Counter)
		self.examples = defaultdict(list)
		self.groups = defaultdict(dict)

	def add(self, row):
		self.photos['total'] += 1
		data = row['detected_objects']
		state = None
		objects = []
		if data is None:
			state = 'sql-null' if row.get('detections_sql_null') else 'json-null-or-unspecified'
		elif not isinstance(data, dict):
			state = 'invalid-container'
		elif 'objects' not in data:
			state = 'missing-objects'
		elif data['objects'] is None:
			state = 'null-objects'
		elif not isinstance(data['objects'], list):
			state = 'invalid-objects'
		else:
			objects = data['objects']
			state = 'nonempty' if objects else 'empty'
		self.photos[state] += 1
		formats = Counter(object_format(o) for o in objects)
		self.formats.update(formats)
		self.photo_formats.update(formats.keys())
		processed_at = utc_datetime(row.get('processed_at'))
		if processed_at is not None:
			for fmt in formats:
				bounds = self.processed_ranges.setdefault(fmt, {'min': processed_at, 'max': processed_at})
				bounds['min'] = min(bounds['min'], processed_at)
				bounds['max'] = max(bounds['max'], processed_at)
		if len(formats) > 1:
			self.photos['mixed-formats'] += 1
		legacy = formats['legacy-no-confidence'] + formats['legacy-confidence']
		if legacy:
			self.photos['with-legacy-objects'] += 1

		dimensions = {key + '_month': month(row.get(key))
		              for key in ('captured_at', 'uploaded_at', 'processed_at')}
		dimensions.update(
			model_name=data.get('model_name') if isinstance(data, dict) else None,
			manual=data.get('manual') if isinstance(data, dict) else None,
			processing_status=row.get('processing_status'), deleted=row.get('deleted'),
		)
		for dimension, value in dimensions.items():
			key = json.dumps(value, sort_keys=True)
			group = self.groups[dimension].setdefault(key, {
				'value': value, 'photos': 0, 'states': Counter(),
				'objects_by_format': Counter(), 'photos_by_format': Counter(),
			})
			group['photos'] += 1
			group['states'][state] += 1
			group['objects_by_format'].update(formats)
			group['photos_by_format'].update(formats.keys())

		seen_issues = set()
		def issue(name, index=None):
			self.issues[name] += 1
			if index is not None:
				self.issue_formats[name][object_format(objects[index])] += 1
			seen_issues.add(name)
			if len(self.examples[name]) < self.example_limit:
				self.examples[name].append({'photo_id': row['id'], 'object_index': index})

		if state in ('invalid-container', 'missing-objects', 'null-objects', 'invalid-objects'):
			issue(state)
		if isinstance(data, dict) and 'manual' in data and type(data['manual']) is not bool:
			issue('invalid-manual')
		for index, obj in enumerate(objects):
			fmt = object_format(obj)
			if fmt.startswith('invalid-'):
				issue(fmt, index)
			if not isinstance(obj, dict):
				continue
			if 'confidence' in obj:
				conf = obj['confidence']
				if conf is None:
					issue('null-confidence', index)
				elif (not finite_number(conf) or not 0 <= conf <= 1) and fmt != 'invalid-confidence':
					issue('invalid-confidence', index)
			for name in bbox_issues(obj, row.get('width'), row.get('height')):
				issue(name, index)
			try:
				blurred = is_blurred(obj)
			except (TypeError, ValueError):
				issue('consumer-read-error', index)
			else:
				self.verdicts['blurred' if blurred else 'visible'] += 1
				self.format_verdicts[fmt]['blurred' if blurred else 'visible'] += 1
		self.issue_photos.update(seen_issues)

	def report(self):
		return {
			'photos': dict(self.photos),
			'objects_by_format': dict(self.formats),
			'photos_by_format': dict(self.photo_formats),
			'objects_by_consumer_verdict': dict(self.verdicts),
			'objects_by_format_and_consumer_verdict': dict(self.format_verdicts),
			'processed_at_range_by_format': {
				fmt: {key: value.isoformat() for key, value in bounds.items()}
				for fmt, bounds in self.processed_ranges.items()
			},
			'issues': {name: {'occurrences': count, 'photos': self.issue_photos[name],
			                  'objects_by_format': dict(self.issue_formats[name]),
			                  'examples': self.examples[name]}
			           for name, count in sorted(self.issues.items())},
			'groups': {name: [groups[k] for k in sorted(groups)]
			           for name, groups in sorted(self.groups.items())},
		}


async def scan_database(url, inventory):
	import asyncpg  # Only needed for a live scan, not for JSONL or unit tests.

	url = url.replace('postgresql+asyncpg://', 'postgresql://', 1)
	conn = await asyncpg.connect(url, server_settings={
		'default_transaction_read_only': 'on', 'application_name': 'detections-inventory',
	})
	try:
		await conn.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
		async with conn.transaction(isolation='repeatable_read', readonly=True):
			metadata = dict(await conn.fetchrow("""
				SELECT current_database() AS database, current_timestamp AS snapshot_at,
				       current_setting('transaction_read_only') AS read_only,
				       current_setting('transaction_isolation') AS isolation,
				       (SELECT data_type FROM information_schema.columns
				        WHERE table_schema='public' AND table_name='photos'
				          AND column_name='detected_objects') AS column_type
			"""))
			async for row in conn.cursor(PHOTO_SQL, prefetch=500):
				inventory.add(dict(row))
			return metadata
	finally:
		await conn.close()


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--source', required=True, help='Human label: prod, local production dump, etc.')
	mode = parser.add_mutually_exclusive_group(required=True)
	mode.add_argument('--database-url-env', help='Name of the environment variable containing the DB URL')
	mode.add_argument('--input', type=Path, help='JSONL photo rows; use - for stdin')
	parser.add_argument('--example-limit', type=int, default=10)
	args = parser.parse_args()
	if args.example_limit < 0:
		parser.error('--example-limit must be nonnegative')
	inventory = Inventory(args.example_limit)
	metadata = {}
	if args.database_url_env:
		url = os.environ.get(args.database_url_env)
		if not url:
			parser.error('The specified database URL environment variable is empty')
		metadata = asyncio.run(scan_database(url, inventory))
	else:
		stream = sys.stdin if str(args.input) == '-' else args.input.open()
		try:
			for line in stream:
				if line.strip():
					inventory.add(json.loads(line))
		finally:
			if stream is not sys.stdin:
				stream.close()
	print(json.dumps({
		'source': args.source, 'generated_at': datetime.now(timezone.utc).isoformat(),
		'blur_confidence': BLUR_CONFIDENCE, 'database_snapshot': metadata,
		**inventory.report(),
	}, indent=2, sort_keys=True, default=str))


if __name__ == '__main__':
	main()
