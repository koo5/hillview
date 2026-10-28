"""Generated detection SQL must preserve verdicts/geometry and restore exact JSON."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import uuid

import asyncpg
import pytest
import pytest_asyncio

SCRIPT = Path(__file__).resolve().parents[1] / 'migrate_detections.py'
spec = importlib.util.spec_from_file_location('sql_migration', SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
from common.legacy_detections import verify_detection_migration  # noqa: E402
from detections_sql import write_export  # noqa: E402


def test_export_is_private_standalone_and_does_not_overwrite(tmp_path):
	before = json.dumps({'model': "O'Reilly\\path $sql$; DROP TABLE photos;-- Ω", 'objects': [
	    {'bbox': {'x1': 1, 'y1': 2, 'x2': 3, 'y2': 4}, 'class_id': 0}]})
	row, _ = migration.plan_row({'id': "a'\\Ω", 'before_text': before})
	row['context'] = {'file_md5': None, 'filename': "a'\\b.exr", 'processed_at': None,
	                  'processing_status': 'completed', 'deleted': False}
	output = tmp_path / 'detections.sql'
	result = write_export([row], source='review\nDROP TABLE photos;', blur_confidence=0.4,
	                      output=output, summary={'photos': 1})
	assert result['photos'] == 1
	assert '-- Source: DROP TABLE photos;' in output.read_text()
	assert output.stat().st_mode & 0o777 == 0o600
	assert output.with_suffix('.verify.sql').exists()
	assert output.with_suffix('.restore.sql').exists()
	assert output.with_suffix('.evidence.json').exists()
	with pytest.raises(ValueError, match='distinct and new'):
		write_export([row], source='review', blur_confidence=0.4, output=output, summary={})


def test_sql_export_is_rejected_with_apply(tmp_path):
	with pytest.raises(ValueError, match='dry-run'):
		asyncio.run(migration.migrate(None, source='test', apply=True, sql_output=tmp_path / 'bad.sql'))


@pytest_asyncio.fixture
async def database():
	url = os.environ.get('DETECTIONS_TEST_ADMIN_URL')
	if not url:
		pytest.skip('DETECTIONS_TEST_ADMIN_URL unset; no database touched')
	admin = await asyncpg.connect(url)
	name = 'detections_sql_test_' + uuid.uuid4().hex
	await admin.execute(f'CREATE DATABASE {name}')
	conn = None
	try:
		conn = await asyncpg.connect(urlunsplit(urlsplit(url)._replace(path='/' + name)))
		await conn.execute('''CREATE TABLE photos (id text PRIMARY KEY,detected_objects json,
		    width int,height int,sizes json,title text,file_md5 text,filename text,
		    processed_at timestamptz,processing_status text,deleted boolean)''')
		objects = {
		    'a': ' { "model": "O\'Reilly\\\\path Ω $sql$; DROP TABLE photos;--", "objects": [{"bbox":{"x1":1,"y1":2,"x2":3,"y2":4},"class_id":0}] } ',
		    'b': '{"objects":[{"confidence":0.9,"blurred":false,"bbox":{"x1":0,"y1":0,"x2":4,"y2":3}}]}',
		    'c': '{"unknown":[1,2],"objects":[{"confidence":0.3,"bbox":{"x1":0,"y1":1,"x2":3,"y2":4}},{"confidence":0.4,"bbox":{"x1":0,"y1":1,"x2":3,"y2":4}}]}',
		    'd': None, 'e': '{}', 'f': '{"objects":[]}',
		    'z': '{"manual":true,"objects":[{"class_id":null,"blur":500,"blurred_from":"operator-history","bbox":{"x1":1,"y1":2,"x2":3,"y2":4}}]}',
		}
		await conn.executemany('''INSERT INTO photos VALUES ($1,$2::json,3840,2880,
		    ' { "full": {"width":3840,"height":2880}, "extra":true } '::json,
		    'untouched','source-md5',$3,'2026-09-02T17:29:13+00:00','completed',$4)''',
		    [(key, text, "O'Reilly\\$sql$.exr", key == 'z') for key, text in objects.items()])
		yield conn
	finally:
		if conn is not None:
			await conn.close()
		await admin.execute(f'DROP DATABASE {name}')
		await admin.close()


async def snapshot(conn):
	return [dict(row) for row in await conn.fetch('''SELECT id,detected_objects::text AS detections,
	    (to_jsonb(p)-'detected_objects')::text AS other_columns, sizes::text AS sizes_text
	    FROM photos p ORDER BY id''')]


async def generate(conn, output):
	async with conn.transaction(readonly=True, isolation='repeatable_read'):
		return await migration.migrate(conn, source='test', sql_output=output, batch_size=2)


@pytest.mark.asyncio
async def test_sql_apply_verification_idempotence_and_exact_restore(database, tmp_path):
	conn = database
	before = await snapshot(conn)
	output = tmp_path / 'detections.sql'
	result = await generate(conn, output)
	assert result['photos_would_change'] == 3
	assert result['objects_added'] == 4
	assert await snapshot(conn) == before
	await conn.execute(output.read_text())
	await conn.execute(output.with_suffix('.verify.sql').read_text())
	after = await snapshot(conn)
	for old, new in zip(before, after):
		assert old['other_columns'] == new['other_columns']
		assert old['sizes_text'] == new['sizes_text']
		verify_detection_migration(json.loads(old['detections']) if old['detections'] else None,
		                           json.loads(new['detections']) if new['detections'] else None)
	assert (await migration.migrate(conn, source='after'))['photos_would_change'] == 0
	assert await conn.fetchval(f"SELECT count(*) FROM {result['sql']['backup_table']}") == 3
	with pytest.raises(asyncpg.DuplicateTableError):
		await conn.execute(output.read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == after
	await conn.execute(output.with_suffix('.restore.sql').read_text())
	assert await snapshot(conn) == before
	await conn.execute(output.with_suffix('.restore.sql').read_text())
	assert await snapshot(conn) == before
	with pytest.raises(asyncpg.RaiseError, match='Later edits'):
		await conn.execute(output.with_suffix('.verify.sql').read_text())
	await conn.execute('ROLLBACK')


@pytest.mark.asyncio
async def test_apply_and_restore_conflicts_roll_back_all_changes(database, tmp_path):
	conn = database
	output = tmp_path / 'detections.sql'
	result = await generate(conn, output)
	await conn.execute("UPDATE photos SET detected_objects='{\"later\":true}'::json WHERE id='z'")
	edited = await snapshot(conn)
	with pytest.raises(asyncpg.RaiseError, match='changed since export'):
		await conn.execute(output.read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == edited
	assert await conn.fetchval('SELECT to_regclass($1)', result['sql']['backup_table']) is None
	# Re-export the changed source, then protect the repair against subsequent edits.
	output = tmp_path / 'current.sql'
	await generate(conn, output)
	await conn.execute(output.read_text())
	await conn.execute("UPDATE photos SET detected_objects='{\"later\":true}'::json WHERE id='c'")
	edited = await snapshot(conn)
	with pytest.raises(asyncpg.RaiseError, match='Later edits'):
		await conn.execute(output.with_suffix('.restore.sql').read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == edited


@pytest.mark.asyncio
async def test_source_identity_guard_and_missing_photo_abort(database, tmp_path):
	conn = database
	output = tmp_path / 'detections.sql'
	await generate(conn, output)
	await conn.execute("UPDATE photos SET file_md5='new-source' WHERE id='z'")
	edited = await snapshot(conn)
	with pytest.raises(asyncpg.RaiseError, match='identity'):
		await conn.execute(output.read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == edited
	await conn.execute("DELETE FROM photos WHERE id='z'")
	edited = await snapshot(conn)
	with pytest.raises(asyncpg.RaiseError, match='Expected 3 planned photos'):
		await conn.execute(output.read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == edited
