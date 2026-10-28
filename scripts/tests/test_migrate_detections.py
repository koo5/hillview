"""Migration invariants and optional PostgreSQL tests in disposable databases.

Set DETECTIONS_TEST_ADMIN_URL to run the DB cases. They CREATE/DROP only uniquely
named test databases, never clear or update the configured source database.
"""

import asyncio
import copy
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
spec = importlib.util.spec_from_file_location('migrate_detections', SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
from common.detections import normalize_detections  # noqa: E402
from common.legacy_detections import verify_detection_migration  # noqa: E402


def detection(**kwargs):
	return {'bbox': {'x1': 0, 'y1': 0, 'x2': 30, 'y2': 20}, 'class_id': 0, **kwargs}


def test_normalization_preserves_existing_fields_flags_provenance_and_order():
	before = {'model_name': 'old-model', 'manual': True, 'extra': {'a': [1]}, 'objects': [
		detection(), detection(confidence=None), detection(confidence=0.4),
		detection(confidence=0.3), detection(confidence=0.9, blurred=False),
		detection(confidence=0.1, blurred=True), detection(blurred_from='operator-history'),
	]}
	untouched = copy.deepcopy(before)
	after = normalize_detections(before)
	assert before == untouched
	assert [o['blurred'] for o in after['objects']] == [True, True, True, False, False, True, True]
	assert after['objects'][0]['blurred_from'] == 'legacy-no-confidence'
	assert after['objects'][2]['blurred_from'] == 'legacy-confidence-0.4'
	assert after['objects'][6]['blurred_from'] == 'operator-history'
	assert after['objects'][4] == before['objects'][4]
	verify_detection_migration(before, after)
	assert normalize_detections(after) is after


@pytest.mark.parametrize('before', [None, {}, {'objects': []}, {'manual': True, 'objects': []}])
def test_empty_records_are_untouched(before):
	assert normalize_detections(before) is before
	verify_detection_migration(before, before)


@pytest.mark.parametrize('before', [
	[], {'objects': None}, {'objects': {}}, {'objects': [None]},
	{'objects': [detection(blurred='false')]}, {'objects': [detection(blurred=1)]},
	{'objects': [detection(confidence='0.9')]}, {'objects': [detection(confidence=True)]},
	{'objects': [detection(confidence=float('nan'))]}, {'objects': [detection(confidence=2)]},
])
def test_invalid_records_are_rejected_without_mutation(before):
	with pytest.raises(ValueError):
		normalize_detections(before)


@pytest.mark.parametrize('edit', ['bbox', 'flag', 'container', 'extra', 'order', 'provenance'])
def test_verifier_catches_representation_and_behavior_changes(edit):
	before = {'model_name': 'old', 'objects': [detection(), detection(confidence=0.3)]}
	after = copy.deepcopy(normalize_detections(before))
	if edit == 'bbox':
		after['objects'][0]['bbox']['x2'] += 1
	elif edit == 'flag':
		after['objects'][1]['blurred'] = True
	elif edit == 'container':
		after['model_name'] = 'new'
	elif edit == 'extra':
		after['objects'][0]['invented'] = True
	elif edit == 'order':
		after['objects'].reverse()
	else:
		del after['objects'][0]['blurred_from']
	with pytest.raises(ValueError, match='verification failed'):
		verify_detection_migration(before, after)


def test_backup_checksum_exclusive_creation_and_private_permissions(tmp_path):
	path = tmp_path / 'batch-1.json'
	document = {'version': 1, 'rows': []}
	migration.save_document(path, document)
	assert path.stat().st_mode & 0o777 == 0o600
	assert migration.read_document(path) == document
	with pytest.raises(FileExistsError):
		migration.save_document(path, document)
	envelope = json.loads(path.read_text())
	envelope['payload']['rows'].append({'tampered': True})
	path.write_text(json.dumps(envelope))
	with pytest.raises(ValueError, match='checksum mismatch'):
		migration.read_document(path)


def test_backup_lock_prevents_overlapping_runs(tmp_path):
	with migration.backup_lock(tmp_path):
		with pytest.raises(BlockingIOError):
			with migration.backup_lock(tmp_path):
				pytest.fail('second run acquired exclusive lock')


@pytest_asyncio.fixture
async def database():
	url = os.environ.get('DETECTIONS_TEST_ADMIN_URL')
	if not url:
		pytest.skip('DETECTIONS_TEST_ADMIN_URL not set; no database touched')
	admin = await asyncpg.connect(url)
	name = 'detections_migration_test_' + uuid.uuid4().hex
	await admin.execute(f'CREATE DATABASE {name}')
	parts = urlsplit(url)
	test_url = urlunsplit(parts._replace(path='/' + name))
	conn = None
	try:
		conn = await asyncpg.connect(test_url)
		await conn.execute('CREATE TABLE public.photos (id text PRIMARY KEY, detected_objects json)')
		values = [None, '{}', '{"objects":[]}',
		          ' { "model_name": "old", "objects" : [ {"class_id":0,"bbox":{"x1":0,"y1":0,"x2":200,"y2":100}} ] } ',
		          json.dumps({'objects': [detection(confidence=0.3), detection(confidence=0.4)]}),
		          json.dumps({'objects': [detection(blurred=False, confidence=0.9)]}),
		          json.dumps({'manual': True, 'objects': [detection(class_id=None, blur=500)]})]
		await conn.executemany('INSERT INTO photos VALUES ($1, $2::json)', [(str(i), v) for i, v in enumerate(values)])
		yield conn, values
	finally:
		if conn is not None:
			await conn.close()
		await admin.execute(f'DROP DATABASE {name}')
		await admin.close()


async def snapshot(conn):
	return [r['value'] for r in await conn.fetch('SELECT detected_objects::text AS value FROM photos ORDER BY id')]


@pytest.mark.asyncio
async def test_dry_run_apply_verify_idempotence_and_exact_restore(database, tmp_path):
	conn, original = database
	dry = await migration.migrate(conn, source='test', batch_size=2)
	assert dry['photos_would_change'] == 3
	assert dry['objects_added'] == 4
	assert dry['blurred_false'] == 1
	assert await snapshot(conn) == original
	backup = tmp_path / 'backup'
	backup.mkdir()
	applied = await migration.migrate(conn, source='test', apply=True, backup_dir=backup, batch_size=2)
	assert applied['photos_changed'] == applied['photos_verified'] == 3
	assert len(migration.load_backups(backup)) == 3
	verified = await migration.restore_or_verify(conn, backup_dir=backup, command='verify')
	assert verified['at_migrated_value'] == 3 and verified['conflicts'] == 0
	second = await migration.migrate(conn, source='test', batch_size=2)
	assert second['photos_would_change'] == 0
	restore_dry = await migration.restore_or_verify(conn, backup_dir=backup, command='restore')
	assert restore_dry['photos_would_restore'] == 3
	assert await snapshot(conn) != original
	await migration.restore_or_verify(conn, backup_dir=backup, command='restore', apply=True)
	assert await snapshot(conn) == original


@pytest.mark.asyncio
async def test_failed_transaction_has_backup_and_resume_skips_committed_batches(database, tmp_path, monkeypatch):
	conn, original = database
	update = migration.update_rows
	calls = 0

	async def interrupt(conn, rows):
		nonlocal calls
		calls += 1
		await update(conn, rows)
		if calls == 2:
			raise RuntimeError('simulated interruption after UPDATE before COMMIT')

	monkeypatch.setattr(migration, 'update_rows', interrupt)
	with pytest.raises(RuntimeError):
		await migration.migrate(conn, source='test', apply=True, backup_dir=tmp_path, batch_size=1)
	current = await snapshot(conn)
	assert current[3] != original[3] and current[4] == original[4]
	assert len(migration.load_backups(tmp_path)) == 2
	monkeypatch.setattr(migration, 'update_rows', update)
	resumed = await migration.migrate(conn, source='test', apply=True, resume=True, backup_dir=tmp_path, batch_size=1)
	assert resumed['photos_changed'] == 2
	assert len(migration.load_backups(tmp_path)) == 3  # duplicate pending backup deduplicated
	await migration.restore_or_verify(conn, backup_dir=tmp_path, command='restore', apply=True)
	assert await snapshot(conn) == original


@pytest.mark.asyncio
async def test_backup_failure_precedes_database_write(database, tmp_path, monkeypatch):
	conn, original = database
	save = migration.save_document

	def fail_batch(path, document):
		if path.name.startswith('batch-'):
			raise OSError('simulated disk full')
		save(path, document)

	monkeypatch.setattr(migration, 'save_document', fail_batch)
	with pytest.raises(OSError, match='disk full'):
		await migration.migrate(conn, source='test', apply=True, backup_dir=tmp_path)
	assert await snapshot(conn) == original


@pytest.mark.asyncio
async def test_restore_refuses_later_edits_and_missing_rows(database, tmp_path):
	conn, _ = database
	await migration.migrate(conn, source='test', apply=True, backup_dir=tmp_path)
	await conn.execute("UPDATE photos SET detected_objects = '{\"objects\":[],\"manual\":true}' WHERE id = '3'")
	await conn.execute("DELETE FROM photos WHERE id = '4'")
	current = await snapshot(conn)
	report = await migration.restore_or_verify(conn, backup_dir=tmp_path, command='restore')
	assert report['conflicts'] == 2
	with pytest.raises(ValueError, match='Restore refused'):
		await migration.restore_or_verify(conn, backup_dir=tmp_path, command='restore', apply=True)
	assert await snapshot(conn) == current


@pytest.mark.asyncio
async def test_compare_and_swap_failure_rolls_back_the_entire_batch(database):
	conn, original = database
	rows = [{'id': '3', 'before_text': original[3], 'after_text': '{"objects":[]}'},
	        {'id': '4', 'before_text': 'stale', 'after_text': '{}'}]
	with pytest.raises(ValueError, match='write verification failed'):
		async with conn.transaction():
			await migration.update_rows(conn, rows)
	assert await snapshot(conn) == original


@pytest.mark.asyncio
async def test_invalid_payload_aborts_batch_and_resume_checks_backup_identity(database, tmp_path):
	conn, original = database
	await conn.execute("UPDATE photos SET detected_objects = '{\"objects\":[{\"blurred\":\"false\"}]}' WHERE id = '4'")
	current = await snapshot(conn)
	with pytest.raises(ValueError, match='Photo 4'):
		await migration.migrate(conn, source='test', apply=True, backup_dir=tmp_path)
	assert await snapshot(conn) == current
	await conn.execute('UPDATE photos SET detected_objects = $1::json WHERE id = $2', original[4], '4')
	with pytest.raises(ValueError, match='original ID range'):
		await migration.migrate(conn, source='test', apply=True, resume=True, backup_dir=tmp_path, after_id='3')


@pytest.mark.asyncio
async def test_row_locks_hold_across_backup_and_write(database, tmp_path, monkeypatch):
	conn, original = database
	# A second connection to the disposable DB, with the same credentials.
	other = await asyncpg.connect(host=conn._addr[0], port=conn._addr[1],
	                              user=conn._params.user, password=conn._params.password,
	                              database=conn._params.database)
	update = migration.update_rows
	writer = None

	async def while_locked(conn, rows):
		nonlocal writer
		writer = asyncio.create_task(other.execute(
			"UPDATE photos SET detected_objects = '{}' WHERE id = '3'"))
		with pytest.raises(asyncio.TimeoutError):
			await asyncio.wait_for(asyncio.shield(writer), timeout=0.1)
		await update(conn, rows)

	monkeypatch.setattr(migration, 'update_rows', while_locked)
	try:
		await migration.migrate(conn, source='test', apply=True, backup_dir=tmp_path)
		await writer
		assert (await snapshot(conn))[3] == '{}'
		assert migration.load_backups(tmp_path)[0]['before_text'] == original[3]
		verified = await migration.restore_or_verify(conn, backup_dir=tmp_path, command='verify')
		assert verified['conflicts'] == 1  # later write is detected, never overwritten
	finally:
		if writer is not None:
			await writer
		await other.close()


@pytest.mark.asyncio
async def test_dry_run_gallery_uses_stored_and_proposed_values_without_writes(database, tmp_path):
	conn, original = database
	await conn.execute('''ALTER TABLE photos ADD captured_at timestamp, ADD processed_at timestamptz,
	    ADD width integer DEFAULT 100, ADD height integer DEFAULT 80,
	    ADD sizes json DEFAULT '{"1024":{"url":"https://pics.example/1024.webp"}}',
	    ADD deleted boolean DEFAULT false''')
	await conn.execute("""UPDATE photos SET processed_at = CASE id
	    WHEN '3' THEN '2026-06-11'::timestamptz WHEN '4' THEN '2026-06-13'::timestamptz
	    WHEN '5' THEN '2026-06-25'::timestamptz ELSE '2026-02-23'::timestamptz END""")
	output = tmp_path / 'review.html'
	async with conn.transaction(isolation='repeatable_read', readonly=True):
		result = await migration.migrate(conn, source='dry-run test', review_html=output, batch_size=2)
		assert await conn.fetchval('SHOW transaction_read_only') == 'on'
	assert await snapshot(conn) == original
	assert result['photos_would_change'] == 3
	assert result['review']['would_change'] == 3
	assert result['review']['controls'] == 1
	html = output.read_text()
	assert 'Dry run: no database rows were changed.' in html
	assert 'Old detections · stored in database' in html
	assert 'New detections · proposed by dry run' in html
	assert 'already explicit control' in html
	assert 'legacy-confidence-0.4' in html
	assert 'Visible legacy detections' in html
	assert not list(tmp_path.glob('batch-*.json'))


def test_cli_rejects_apply_with_review_before_creating_a_backup(tmp_path, monkeypatch):
	backup = tmp_path / 'backup'
	monkeypatch.setenv('REVIEW_TEST_DB', 'postgresql://localhost/example')
	monkeypatch.setattr(migration.sys, 'argv', ['migrate_detections.py', 'migrate', '--apply',
	    '--database-url-env', 'REVIEW_TEST_DB', '--source', 'test', '--backup-dir', str(backup),
	    '--review-html', str(tmp_path / 'review.html')])
	with pytest.raises(SystemExit) as exc:
		migration.main()
	assert exc.value.code == 2
	assert not backup.exists()
