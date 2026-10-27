"""Offline coverage for the migration inventory; no application DB fixtures."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'inventory_detections.py'
spec = importlib.util.spec_from_file_location('inventory_detections', SCRIPT)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

BOX = {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 80}


def photo(data, **kwargs):
	return {'id': 'p1', 'detected_objects': data, 'width': 100, 'height': 80,
	        'captured_at': '2026-01-01T00:30:00+01:00',
	        'uploaded_at': '2026-07-01T00:00:00Z', **kwargs}


def obj(**kwargs):
	return {'bbox': dict(BOX), **kwargs}


def test_mixed_formats_threshold_and_explicit_overrides_do_not_mutate():
	data = {'manual': True, 'model_name': 'old-model', 'objects': [
		obj(), obj(confidence=0.39), obj(confidence=0.4),
		obj(confidence=0.9, blurred=False), obj(blurred=True),
	]}
	before = json.dumps(data)
	report = inventory.Inventory()
	report.add(photo(data, processed_at='2026-06-01T01:00:00+01:00'))
	out = report.report()
	assert out['objects_by_format'] == {
		'legacy-no-confidence': 1, 'legacy-confidence': 2, 'explicit': 2,
	}
	assert out['photos_by_format'] == dict.fromkeys(out['objects_by_format'], 1)
	assert out['objects_by_consumer_verdict'] == {'blurred': 3, 'visible': 2}
	assert out['objects_by_format_and_consumer_verdict']['legacy-confidence'] == {'blurred': 1, 'visible': 1}
	assert out['processed_at_range_by_format']['explicit']['min'] == '2026-06-01T00:00:00+00:00'
	assert out['photos']['mixed-formats'] == 1
	assert out['photos']['with-legacy-objects'] == 1
	assert out['groups']['captured_at_month'][0]['value'] == '2025-12'
	assert out['groups']['uploaded_at_month'][0]['value'] == '2026-07'
	assert out['groups']['manual'][0]['value'] is True
	assert json.dumps(data) == before
	assert out['issues'] == {}


@pytest.mark.parametrize(('data', 'state'), [
	(None, 'json-null-or-unspecified'), ([], 'invalid-container'),
	({}, 'missing-objects'), ({'objects': None}, 'null-objects'),
	({'objects': {}}, 'invalid-objects'), ({'objects': []}, 'empty'),
])
def test_empty_and_invalid_containers_are_distinguished(data, state):
	report = inventory.Inventory()
	report.add(photo(data))
	assert report.report()['photos'][state] == 1
	assert report.report()['objects_by_format'] == {}


def test_sql_null_is_distinct_from_json_null():
	report = inventory.Inventory()
	report.add(photo(None, detections_sql_null=True))
	assert report.report()['photos']['sql-null'] == 1


@pytest.mark.parametrize(('box', 'issues'), [
	(BOX, []),
	(None, ['bbox-malformed']),
	({'x1': False, 'y1': 0, 'x2': 1, 'y2': 1}, ['bbox-malformed']),
	({'x1': 0, 'y1': 0, 'x2': float('nan'), 'y2': 1}, ['bbox-malformed']),
	({'x1': -1, 'y1': 0, 'x2': 101, 'y2': 0},
	 ['bbox-empty-or-reversed', 'bbox-negative', 'bbox-exceeds-image']),
	({'x1': 0.5, 'y1': 0, 'x2': 1, 'y2': 1}, ['bbox-non-integer']),
])
def test_bbox_validation(box, issues):
	assert inventory.bbox_issues({'bbox': box}, 100, 80) == issues


def test_unknown_dimensions_do_not_invent_bounds():
	assert inventory.bbox_issues(obj(), None, 80) == ['bbox-bounds-unknown']


def test_invalid_objects_and_eager_consumer_fallback_are_reported_without_aborting():
	report = inventory.Inventory(example_limit=1)
	for _ in range(2):
		report.add(photo({'objects': [
			None, obj(confidence='bad', blurred=True), obj(blurred='false'),
			obj(confidence=None), obj(confidence=2), obj(confidence=True),
		]}))
	out = report.report()
	assert out['issues']['consumer-read-error']['occurrences'] == 2
	assert out['issues']['invalid-confidence']['occurrences'] == 6
	assert out['issues']['invalid-confidence']['photos'] == 2
	assert len(out['issues']['invalid-confidence']['examples']) == 1
	assert out['issues']['invalid-blurred']['occurrences'] == 2
	assert out['issues']['null-confidence']['occurrences'] == 2
	assert out['objects_by_format']['invalid-object'] == 2


@pytest.mark.asyncio
async def test_database_scan_enforces_read_only_snapshot_and_decodes_json(monkeypatch):
	import asyncpg

	class Transaction:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			pass

	class Connection:
		set_type_codec = AsyncMock()
		fetchrow = AsyncMock(return_value={'read_only': 'on', 'column_type': 'json'})
		close = AsyncMock()

		def transaction(self, **kwargs):
			assert kwargs == {'isolation': 'repeatable_read', 'readonly': True}
			return Transaction()

		async def cursor(self, sql, **kwargs):
			assert sql == inventory.PHOTO_SQL
			yield photo({'objects': [obj()]})

	conn = Connection()
	connect = AsyncMock(return_value=conn)
	monkeypatch.setattr(asyncpg, 'connect', connect)
	report = inventory.Inventory()
	metadata = await inventory.scan_database('postgresql+asyncpg://localhost/test', report)
	assert connect.call_args.args == ('postgresql://localhost/test',)
	assert connect.call_args.kwargs['server_settings']['default_transaction_read_only'] == 'on'
	assert metadata['column_type'] == 'json'
	assert report.report()['photos']['total'] == 1
	conn.close.assert_awaited_once()
	assert conn.set_type_codec.call_args.args == ('json',)
