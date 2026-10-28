"""Size repair invariants; DB tests create/drop only unique disposable databases."""
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

SCRIPT = Path(__file__).resolve().parents[1] / 'fix_photo_sizes.py'
spec = importlib.util.spec_from_file_location('fix_photo_sizes', SCRIPT)
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)
from propose_photo_size_fixes import build_proposal  # noqa: E402

STAMP = '2026-09-02 17:29:13.422469+00:00'


def example(kind='row', row_id='a'):
	if kind == 'panorama':
		old, full = [156962, 8366], [8192, 554]
	elif kind == 'rendition':
		old, full = [2560, 1440], [2560, 1440]
	else:
		old, full = [1440, 2560], [2560, 1440]
	url = f'https://pics.example/{row_id}/full.webp'
	meta = {'full': {'width': full[0], 'height': full[1], 'url': url, 'extra': 'preserve'},
	        '320': {'width': 180 if kind == 'rendition' else 320,
	                'height': 320 if kind == 'rendition' else 180,
	                'url': f'https://pics.example/{row_id}/320.webp', 'extra': [1, 2]},
	        'other': {'unknown': True}}
	item = {'id': row_id, 'classification': 'other-aspect-mismatch' if kind == 'panorama' else
	        'exact-match' if kind == 'rendition' else 'exact-width-height-reversal',
	        'photo_dimensions': old, 'full_dimensions': full, 'full_url': url,
	        'ordinary_renditions': [{'name': '320', 'dimensions': [meta['320']['width'], meta['320']['height']],
	                                 'url': meta['320']['url']}],
	        'ordinary_aspect_disagrees_full': kind == 'rendition', 'deleted': False,
	        'processed_at': STAMP, 'orientation': None, 'detections': 0}
	checks = {(row_id, 'sizes.full'): {'actual_dimensions': full},
	          (row_id, 'sizes.320'): {'actual_dimensions': [320, 180]}}
	dzi, source = None, None
	if kind == 'panorama':
		meta['full']['pyramid'] = {'width': 157180, 'height': 10646,
		                         'dzi_url': f'https://pics.example/{row_id}/image.dzi'}
		dzi = {'id': row_id, 'actual_dzi_dimensions': {'Width': '157180', 'Height': '10646'},
		       'full': {'pyramid': meta['full']['pyramid']}}
		source = {'id': row_id, 'dimensions': old, 'matches_photo_file_md5': True, 'file_md5': 'source-md5'}
	photo = build_proposal(item, checks, dzi, source, match_uploaded_artifacts=True)
	row = {'id': row_id, 'width': old[0], 'height': old[1], 'sizes_text': json.dumps(meta, indent=2),
	       'processed_at': fix.timestamp(STAMP), 'file_md5': 'source-md5', 'filename': 'source.exr',
	       'processing_status': 'completed', 'deleted': False}
	return row, photo


def plan_for(*photos):
	return {'version': 2, 'dimension_basis': 'uploaded-artifacts', 'photos': list(photos)}


def test_only_reviewed_dimensions_change_and_raw_json_survives_row_only_repair():
	row, photo = example('panorama')
	before = copy.deepcopy(row)
	after = fix.plan_state(row, photo)
	assert row == before
	assert [after['width'], after['height']] == [157180, 10646]
	assert after['sizes_text'] == row['sizes_text']
	row, photo = example('rendition')
	after = fix.plan_state(row, photo)
	expected = json.loads(row['sizes_text'])
	expected['320']['width'], expected['320']['height'] = 320, 180
	assert json.loads(after['sizes_text']) == expected
	assert after['width'] == row['width'] and after['height'] == row['height']
	assert fix.plan_state({**row, **after}, photo) == after


@pytest.mark.parametrize('edit', ['timestamp', 'url', 'dimensions', 'md5', 'deleted'])
def test_changed_rows_are_rejected(edit):
	row, photo = example('panorama')
	if edit == 'timestamp':
		row['processed_at'] = fix.timestamp('2026-09-03T00:00:00+00:00')
	elif edit == 'url':
		sizes = json.loads(row['sizes_text'])
		sizes['full']['pyramid']['dzi_url'] = 'https://other.example/changed.dzi'
		row['sizes_text'] = json.dumps(sizes)
	elif edit == 'dimensions':
		row['height'] += 1
	elif edit == 'md5':
		row['file_md5'] = 'changed'
	else:
		row['deleted'] = True
	with pytest.raises(ValueError):
		fix.plan_state(row, photo)


def test_old_plans_and_invalid_changes_are_rejected_but_blocked_photos_are_skipped():
	_, photo = example()
	with pytest.raises(ValueError, match='version 2'):
		fix.selected_photos({'version': 1, 'photos': [photo]})
	for key, value in [('path', 'detected_objects'), ('after', [True, 1440]), ('status', 'needs-check')]:
		bad = copy.deepcopy(photo)
		bad['changes'][0][key] = value
		with pytest.raises(ValueError):
			fix.selected_photos(plan_for(bad))
	assert fix.selected_photos(plan_for({**photo, 'status': 'blocked'})) == []
	with pytest.raises(ValueError, match='repeated'):
		fix.selected_photos(plan_for(photo, photo))


def test_dzi_header_check_accepts_only_matching_descriptor(monkeypatch):
	from io import BytesIO

	data = b'<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"><Size Width="157180" Height="10646"/></Image>'
	monkeypatch.setattr(fix, 'urlopen', lambda *a, **kw: BytesIO(data))
	artifact = {'kind': 'dzi', 'url': 'https://pics.example/image.dzi', 'dimensions': [157180, 10646]}
	assert fix.check_artifact(artifact)['dimensions'] == [157180, 10646]
	with pytest.raises(ValueError, match='Artifact changed'):
		fix.check_artifact({**artifact, 'dimensions': [156962, 8366]})


@pytest_asyncio.fixture
async def database():
	url = os.environ.get('DETECTIONS_TEST_ADMIN_URL')
	if not url:
		pytest.skip('DETECTIONS_TEST_ADMIN_URL unset; no database touched')
	admin = await asyncpg.connect(url)
	name = 'photo_sizes_test_' + uuid.uuid4().hex
	await admin.execute(f'CREATE DATABASE {name}')
	conn = None
	try:
		conn = await asyncpg.connect(urlunsplit(urlsplit(url)._replace(path='/' + name)))
		await conn.execute('''CREATE TABLE photos (id text PRIMARY KEY, width int, height int,
		    sizes json, detected_objects json, file_md5 text, filename text, processed_at timestamptz,
		    processing_status text, deleted boolean, title text)''')
		photos = []
		for kind, row_id in [('row', 'a'), ('rendition', 'b'), ('panorama', 'c')]:
			row, photo = example(kind, row_id)
			await conn.execute('''INSERT INTO photos VALUES ($1,$2,$3,$4::json,$5::json,$6,$7,$8,$9,$10,$11)''',
			    row_id, row['width'], row['height'], row['sizes_text'],
			    ' { "manual": true, "objects": [{"bbox":{"x1":1,"y1":2,"x2":3,"y2":4},"blurred":false}] } ',
			    row['file_md5'], row['filename'], row['processed_at'], 'completed', False, 'untouched')
			photos.append(photo)
		yield conn, plan_for(*photos)
	finally:
		if conn is not None:
			await conn.close()
		await admin.execute(f'DROP DATABASE {name}')
		await admin.close()


async def snapshot(conn):
	return [dict(r) for r in await conn.fetch('''SELECT id,width,height,sizes::text AS sizes_text,
	    detected_objects::text AS detections,title FROM photos ORDER BY id''')]


@pytest.mark.asyncio
async def test_real_apply_verify_idempotence_and_exact_restore(database, tmp_path, monkeypatch):
	conn, plan = database
	before = await snapshot(conn)
	assert (await fix.repair(conn, plan))['photos_would_change'] == 3
	assert await snapshot(conn) == before
	checked = []
	monkeypatch.setattr(fix, 'recheck_artifacts', lambda photos: checked.extend(photos) or [])
	assert (await fix.repair(conn, plan, apply=True, backup_dir=tmp_path))['photos_changed'] == 3
	assert len(checked) == 3
	after = await snapshot(conn)
	assert [(r['detections'], r['title']) for r in after] == [(r['detections'], r['title']) for r in before]
	assert after[0]['sizes_text'] == before[0]['sizes_text']
	assert after[2]['sizes_text'] == before[2]['sizes_text']
	assert [after[2]['width'], after[2]['height']] == [157180, 10646]
	assert (await fix.backup_operation(conn, tmp_path))['at_repaired_value'] == 3
	assert (await fix.repair(conn, plan))['already_matching'] == 3
	assert (await fix.backup_operation(conn, tmp_path, restore=True))['at_repaired_value'] == 3
	assert await snapshot(conn) == after
	await fix.backup_operation(conn, tmp_path, restore=True, apply=True)
	assert await snapshot(conn) == before
	assert (tmp_path / 'repair.json').stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_conflicting_plan_and_failed_backup_make_no_writes(database, tmp_path, monkeypatch):
	conn, plan = database
	monkeypatch.setattr(fix, 'recheck_artifacts', lambda photos: [])
	before = await snapshot(conn)
	plan['photos'][-1]['processed_at'] = '2026-09-03T00:00:00+00:00'
	with pytest.raises(ValueError, match='timestamp changed'):
		await fix.repair(conn, plan, apply=True, backup_dir=tmp_path)
	assert await snapshot(conn) == before
	plan['photos'][-1]['processed_at'] = STAMP
	monkeypatch.setattr(fix, 'save_document', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
	with pytest.raises(OSError, match='disk full'):
		await fix.repair(conn, plan, apply=True, backup_dir=tmp_path)
	assert await snapshot(conn) == before


@pytest.mark.asyncio
async def test_guarded_restore_rolls_back_all_rows_on_later_edit(database, tmp_path, monkeypatch):
	conn, plan = database
	monkeypatch.setattr(fix, 'recheck_artifacts', lambda photos: [])
	await fix.repair(conn, plan, apply=True, backup_dir=tmp_path)
	await conn.execute("UPDATE photos SET sizes=json_build_object('later',true) WHERE id='c'")
	edited = await snapshot(conn)
	with pytest.raises(ValueError, match='later metadata edits'):
		await fix.backup_operation(conn, tmp_path, restore=True, apply=True)
	assert await snapshot(conn) == edited


def test_sql_export_needs_no_database_and_refuses_to_overwrite(tmp_path):
	import subprocess
	import sys

	_, photo = example('panorama')
	plan = tmp_path / 'plan.json'
	plan.write_text(json.dumps(plan_for(photo)))
	output = tmp_path / 'repair.sql'
	result = subprocess.run([sys.executable, str(SCRIPT), 'sql', '--plan', str(plan), '--output', str(output)],
	                        capture_output=True, text=True, env={})
	assert result.returncode == 0, result.stderr
	summary = json.loads(result.stdout)
	assert summary['selected_photos'] == 1
	assert output.read_text().startswith('-- Photo dimensions')
	assert output.stat().st_mode & 0o777 == 0o600
	assert output.with_suffix('.verify.sql').exists()
	assert output.with_suffix('.restore.sql').exists()
	assert output.with_suffix('.evidence.json').exists()
	with pytest.raises(ValueError, match='distinct and new'):
		fix.export_sql(plan_for(photo), output)


@pytest.mark.asyncio
async def test_sql_apply_verify_restore_and_quoting(database, tmp_path):
	conn, plan = database
	# Literal quotes, backslashes, SQL text, Unicode and dollar quotes are data.
	url = "https://pics.example/a/O'Reilly\\part?$sql$;DROP TABLE photos;--Ω"
	photo = plan['photos'][0]
	photo['full_url'] = photo['changes'][0]['artifact']['url'] = url
	sizes = json.loads(await conn.fetchval("SELECT sizes::text FROM photos WHERE id='a'"))
	sizes['full']['url'] = url
	await conn.execute("UPDATE photos SET sizes=$1::json WHERE id='a'", json.dumps(sizes, indent=2))
	before = await snapshot(conn)
	output = tmp_path / 'repair.sql'
	summary = fix.export_sql(plan, output)
	await conn.execute(output.read_text())
	await conn.execute(output.with_suffix('.verify.sql').read_text())
	after = await snapshot(conn)
	assert [(r['detections'], r['title']) for r in after] == [(r['detections'], r['title']) for r in before]
	assert after[0]['sizes_text'] == before[0]['sizes_text']
	assert after[2]['sizes_text'] == before[2]['sizes_text']
	assert [after[2]['width'], after[2]['height']] == [157180, 10646]
	expected = json.loads(before[1]['sizes_text'])
	expected['320']['width'], expected['320']['height'] = 320, 180
	assert json.loads(after[1]['sizes_text']) == expected
	assert await conn.fetchval(f"SELECT count(*) FROM {summary['backup_table']}") == 3
	with pytest.raises(asyncpg.DuplicateTableError):
		await conn.execute(output.read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == after
	await conn.execute(output.with_suffix('.restore.sql').read_text())
	assert await snapshot(conn) == before
	await conn.execute(output.with_suffix('.restore.sql').read_text())
	assert await snapshot(conn) == before
	with pytest.raises(asyncpg.RaiseError, match='metadata differs'):
		await conn.execute(output.with_suffix('.verify.sql').read_text())
	await conn.execute('ROLLBACK')


@pytest.mark.asyncio
async def test_sql_conflicts_roll_back_apply_and_restore(database, tmp_path):
	conn, plan = database
	before = await snapshot(conn)
	bad = copy.deepcopy(plan)
	bad['photos'][-1]['processed_at'] = '2026-09-03T00:00:00+00:00'
	output = tmp_path / 'bad.sql'
	summary = fix.export_sql(bad, output)
	with pytest.raises(asyncpg.RaiseError, match='identity/status changed'):
		await conn.execute(output.read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == before
	assert await conn.fetchval('SELECT to_regclass($1)', summary['backup_table']) is None
	output = tmp_path / 'good.sql'
	fix.export_sql(plan, output)
	await conn.execute(output.read_text())
	await conn.execute("UPDATE photos SET sizes=json_build_object('later',true) WHERE id='c'")
	edited = await snapshot(conn)
	with pytest.raises(asyncpg.RaiseError, match='metadata differs'):
		await conn.execute(output.with_suffix('.restore.sql').read_text())
	await conn.execute('ROLLBACK')
	assert await snapshot(conn) == edited
