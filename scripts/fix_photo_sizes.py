#!/usr/bin/env python3
"""Apply a reviewed uploaded-artifact size plan, with exact backups and restore.

repair and restore default to dry run. repair --apply rechecks served image/DZI
headers, locks all selected rows, validates their plan preconditions, fsyncs a
private backup, then commits all changes in one transaction. Only width, height
and sizes may be written. No dotenv loading or implicit database target.
sql generates standalone apply/verify/restore SQL without a database connection.
"""
import argparse
import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_photo_dimensions import dimensions
from migrate_detections import backup_lock, encode, now, read_document, save_document, sync_directory
from photo_dimension_headers import check_image

KIND = 'photo-size-repair'
COLUMNS = '''id, width, height, sizes::text AS sizes_text, file_md5, filename,
             processed_at, processing_status, deleted'''


def valid_pair(pair):
	return isinstance(pair, list) and len(pair) == 2 and dimensions(*pair) is not None


def field_variant(path):
	if path == 'photos.width/height':
		return None
	match = re.fullmatch(r'sizes\.([0-9]+)\.width/height', path)
	if not match:
		raise ValueError(f'Unsupported repair field: {path}')
	return match[1]


def selected_photos(plan):
	if plan.get('version') != 2 or plan.get('dimension_basis') != 'uploaded-artifacts':
		raise ValueError('Need a version 2 plan generated with --match-uploaded-artifacts')
	photos, seen = [], set()
	for photo in plan['photos']:
		if not isinstance(photo.get('id'), str) or photo['id'] in seen:
			raise ValueError('Invalid or repeated photo ID')
		seen.add(photo['id'])
		if photo.get('status') != 'verified' or photo.get('deleted'):
			continue
		if not photo.get('changes') or photo.get('issues'):
			raise ValueError(f'{photo["id"]}: verified photo has no changes or has unresolved issues')
		fields = set()
		for change in photo['changes']:
			variant = field_variant(change['path'])
			artifact = change.get('artifact') or {}
			if (change['path'] in fields or change.get('status') != 'verified'
			    or not valid_pair(change.get('before')) or not valid_pair(change.get('after'))
			    or artifact.get('dimensions') != change['after']
			    or artifact.get('kind') not in ('image', 'dzi')
			    or (variant is not None and artifact['kind'] != 'image')
			    or not isinstance(artifact.get('url'), str)
			    or urlsplit(artifact['url']).scheme not in ('http', 'https')
			    or not urlsplit(artifact['url']).netloc):
				raise ValueError(f'{photo["id"]}: invalid, repeated or unverified change')
			fields.add(change['path'])
		photos.append(photo)
	return photos


def check_artifact(artifact):
	if artifact['kind'] == 'image':
		result = check_image({'id': '', 'field': '', 'url': artifact['url'],
		                      'expected_dimensions': artifact['dimensions']})
		if result.get('error'):
			raise ValueError(f'Artifact header check failed: {artifact["url"]}: {result["error"]}')
		actual = result['actual_dimensions']
	else:
		request = Request(artifact['url'], headers={'Accept-Encoding': 'identity',
		                                          'User-Agent': 'Hillview-size-repair/1'})
		with urlopen(request, timeout=12) as response:
			data = response.read(65537)
		if len(data) > 65536:
			raise ValueError('DZI descriptor exceeds 64 KiB')
		size = ET.fromstring(data).find('{http://schemas.microsoft.com/deepzoom/2008}Size')
		if size is None:
			raise ValueError('DZI descriptor has no Size')
		actual = [int(size.get('Width')), int(size.get('Height'))]
	if actual != artifact['dimensions']:
		raise ValueError(f'Artifact changed: {artifact["url"]}: expected {artifact["dimensions"]}, got {actual}')
	return {'url': artifact['url'], 'kind': artifact['kind'], 'dimensions': actual, 'checked_at': now()}


def recheck_artifacts(photos):
	artifacts = {encode(c['artifact']): c['artifact'] for p in photos for c in p['changes']}
	with ThreadPoolExecutor(max_workers=6) as pool:
		return list(pool.map(check_artifact, artifacts.values()))


def state(row):
	return {key: row[key] for key in ('width', 'height', 'sizes_text')}


def context(row):
	return {key: str(row[key]) if key == 'processed_at' else row[key]
	        for key in ('file_md5', 'filename', 'processed_at', 'processing_status', 'deleted')}


def timestamp(value):
	return datetime.fromisoformat(str(value).replace('Z', '+00:00'))


def plan_state(row, photo):
	"""Validate current identity/geometry and change only the reviewed dimensions."""
	if row['processing_status'] != 'completed' or row['deleted'] != photo['deleted']:
		raise ValueError(f'{row["id"]}: status/deletion changed')
	if timestamp(row['processed_at']) != timestamp(photo['processed_at']):
		raise ValueError(f'{row["id"]}: processing timestamp changed')
	source = photo.get('original_source_evidence') or {}
	if source.get('matches_photo_file_md5') and source.get('file_md5') != row['file_md5']:
		raise ValueError(f'{row["id"]}: source MD5 changed')
	before = state(row)
	after = dict(before)
	allowed_photo_sizes = [photo['photo_dimensions']]
	allowed_photo_sizes.extend(c['after'] for c in photo['changes'] if c['path'] == 'photos.width/height')
	if [row['width'], row['height']] not in allowed_photo_sizes:
		raise ValueError(f'{row["id"]}: photo dimensions changed since the reviewed plan')
	sizes = json.loads(before['sizes_text'])
	full = sizes.get('full') or {}
	if [full.get('width'), full.get('height')] != photo['full_dimensions'] or full.get('url') != photo['full_url']:
		raise ValueError(f'{row["id"]}: full rendition changed')
	for change in photo['changes']:
		variant = field_variant(change['path'])
		artifact = change['artifact']
		if variant is None:
			current = [after['width'], after['height']]
			basis = (full.get('pyramid') or {}) if artifact['kind'] == 'dzi' else full
			url_key = 'dzi_url' if artifact['kind'] == 'dzi' else 'url'
			if basis.get(url_key) != artifact['url'] or [basis.get('width'), basis.get('height')] != change['after']:
				raise ValueError(f'{row["id"]}: row-dimension artifact basis changed')
		else:
			entry = sizes.get(variant) or {}
			current = [entry.get('width'), entry.get('height')]
			if entry.get('url') != artifact['url']:
				raise ValueError(f'{row["id"]}: rendition URL changed')
		if current == change['after']:
			continue
		if current != change['before']:
			raise ValueError(f'{row["id"]}: {change["path"]} changed since the reviewed plan')
		if variant is None:
			after['width'], after['height'] = change['after']
		else:
			entry['width'], entry['height'] = change['after']
	if sizes != json.loads(before['sizes_text']):
		after['sizes_text'] = encode(sizes)
	return after


async def identity(conn):
	return dict(await conn.fetchrow('''SELECT current_database() AS database,
	    inet_server_addr()::text AS server_address, inet_server_port() AS server_port,
	    (SELECT data_type FROM information_schema.columns WHERE table_schema='public'
	     AND table_name='photos' AND column_name='sizes') AS sizes_type'''))


async def write_state(conn, row_id, before, after):
	result = await conn.fetchrow('''UPDATE public.photos SET width=$2, height=$3, sizes=$4::json
	    WHERE id=$1 AND width IS NOT DISTINCT FROM $5 AND height IS NOT DISTINCT FROM $6
	    AND sizes::text IS NOT DISTINCT FROM $7
	    RETURNING width, height, sizes::text AS sizes_text''', row_id, after['width'], after['height'],
	    after['sizes_text'], before['width'], before['height'], before['sizes_text'])
	if result is None or dict(result) != after:
		raise ValueError(f'{row_id}: update verification failed; transaction will roll back')


async def repair(conn, plan, *, apply=False, backup_dir=None, check_artifacts=False):
	photos = selected_photos(plan)
	if apply and backup_dir is None:
		raise ValueError('--apply requires --backup-dir')
	checks = await asyncio.to_thread(recheck_artifacts, photos) if apply or check_artifacts else []
	db = await identity(conn)
	if db['sizes_type'] != 'json':
		raise ValueError('Expected photos.sizes to be json')
	changes = []
	async with conn.transaction(readonly=not apply, isolation='repeatable_read'):
		rows = await conn.fetch(f'SELECT {COLUMNS} FROM public.photos WHERE id=ANY($1::text[]) ORDER BY id'
		                        + (' FOR UPDATE' if apply else ''), [p['id'] for p in photos])
		by_id = {r['id']: r for r in rows}
		if len(by_id) != len(photos):
			raise ValueError('A reviewed photo no longer exists; nothing applied')
		for photo in photos:
			row = by_id[photo['id']]
			after = plan_state(row, photo)
			if after != state(row):
				changes.append({'id': row['id'], 'before': state(row), 'after': after, 'context': context(row)})
		if apply:
			save_document(backup_dir / 'repair.json', {'kind': KIND, 'version': 1, 'created_at': now(),
			    'database': db, 'plan_sha256': hashlib.sha256(encode(plan).encode()).hexdigest(),
			    'plan': plan, 'artifact_checks': checks, 'rows': changes})
			for change in changes:
				await write_state(conn, change['id'], change['before'], change['after'])
	return {'mode': 'apply' if apply else 'dry-run', 'database': db, 'selected_photos': len(photos),
	        'skipped_photos': len(plan['photos']) - len(photos),
	        'photos_changed' if apply else 'photos_would_change': len(changes),
	        'already_matching': len(photos) - len(changes), 'artifact_headers_rechecked': len(checks),
	        'field_pairs': sum(len(p['changes']) for p in photos)}


async def backup_operation(conn, backup_dir, *, restore=False, apply=False):
	document = read_document(backup_dir / 'repair.json')
	if document.get('kind') != KIND or document.get('version') != 1:
		raise ValueError('Unsupported size-repair backup')
	if document['database'] != await identity(conn):
		raise ValueError('Backup database identity differs from target')
	counts = Counter()
	async with conn.transaction(readonly=not apply, isolation='repeatable_read'):
		for saved in sorted(document['rows'], key=lambda row: row['id']):
			row = await conn.fetchrow(f'SELECT {COLUMNS} FROM public.photos WHERE id=$1'
			                          + (' FOR UPDATE' if apply else ''), saved['id'])
			if row is None or context(row) != saved['context']:
				raise ValueError(f'{saved["id"]}: photo identity/status changed; nothing applied')
			current = state(row)
			if current == saved['after']:
				counts['at_repaired_value'] += 1
				if restore and apply:
					await write_state(conn, saved['id'], current, saved['before'])
			elif current == saved['before']:
				counts['at_original_value'] += 1
			else:
				raise ValueError(f'{saved["id"]}: later metadata edits conflict; nothing applied')
	return {'mode': 'restore-apply' if apply else 'restore-dry-run' if restore else 'verify', **counts}


async def run(args):
	import asyncpg
	conn = await asyncpg.connect(os.environ[args.database_url_env])
	try:
		if args.command == 'repair':
			return await repair(conn, json.loads(args.plan.read_text()), apply=args.apply,
			                    backup_dir=args.backup_dir, check_artifacts=args.check_artifacts)
		return await backup_operation(conn, args.backup_dir, restore=args.command == 'restore', apply=args.apply)
	finally:
		await conn.close()


def export_sql(plan, output, *, check_artifacts=False):
	from photo_size_sql import bundle

	photos = selected_photos(plan)
	checks = recheck_artifacts(photos) if check_artifacts else []
	summary = f'{len(checks)} live artifact headers checked; completed {now()}.' if check_artifacts else 'Uses saved reviewed artifact evidence; HTTP headers not rechecked at generation.'
	scripts = bundle(encode(plan), json.dumps(photos, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2), len(photos), summary)
	paths = {'apply': output, 'verify': output.with_suffix('.verify.sql'),
	         'restore': output.with_suffix('.restore.sql'), 'evidence': output.with_suffix('.evidence.json')}
	if len(set(paths.values())) != len(paths) or any(p.exists() or p.is_symlink() for p in paths.values()):
		raise ValueError('SQL output files must be distinct and new')
	output.parent.mkdir(parents=True, exist_ok=True)
	for name, path in paths.items():
		content = encode({'plan': plan, 'artifact_checks': checks, 'backup_table': scripts['backup_table'],
		                  'plan_sha256': scripts['plan_sha256'], 'generated_at': now()}) + '\n' if name == 'evidence' else scripts[name]
		fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, 'w') as stream:
			stream.write(content)
	return {'files': {key: str(path) for key, path in paths.items()},
	        'backup_table': 'public.' + scripts['backup_table'], 'selected_photos': len(photos),
	        'field_pairs': sum(len(p['changes']) for p in photos),
	        'skipped_photos': len(plan['photos']) - len(photos), 'artifact_headers_rechecked': len(checks)}


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	commands = parser.add_subparsers(dest='command', required=True)
	sql = commands.add_parser('sql', help='Generate standalone SQL files; no database URL required')
	sql.add_argument('--plan', type=Path, required=True)
	sql.add_argument('--output', type=Path, required=True)
	sql.add_argument('--check-artifacts', action='store_true', help='Recheck served headers now; SQL execution checks database preconditions only')
	for name in ('repair', 'restore', 'verify'):
		sub = commands.add_parser(name)
		sub.add_argument('--database-url-env', required=True)
		sub.add_argument('--backup-dir', type=Path, required=name != 'repair')
		mode = sub.add_mutually_exclusive_group()
		mode.add_argument('--dry-run', action='store_true')
		if name != 'verify':
			mode.add_argument('--apply', action='store_true')
		sub.set_defaults(apply=False)
		if name == 'repair':
			sub.add_argument('--plan', type=Path, required=True)
			sub.add_argument('--check-artifacts', action='store_true', help='Recheck HTTP headers during dry run; automatic with --apply')
	args = parser.parse_args()
	if args.command == 'sql':
		try:
			result = export_sql(json.loads(args.plan.read_text()), args.output, check_artifacts=args.check_artifacts)
		except (ValueError, OSError) as exc:
			parser.exit(2, f'{exc}\n')
		print(json.dumps(result, indent=2, sort_keys=True))
		return
	if not os.environ.get(args.database_url_env):
		parser.error('Specified database URL environment variable is empty')
	if args.command == 'repair' and args.apply:
		if args.backup_dir is None:
			parser.error('--apply requires a new --backup-dir')
		args.backup_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
		sync_directory(args.backup_dir.parent)
	try:
		if args.backup_dir is not None:
			with backup_lock(args.backup_dir):
				result = asyncio.run(run(args))
		else:
			result = asyncio.run(run(args))
	except (ValueError, OSError) as exc:
		parser.exit(2, f'{exc}\n')
	print(json.dumps(result, indent=2, sort_keys=True))
	if args.command == 'verify' and result.get('at_original_value'):
		raise SystemExit(2)


if __name__ == '__main__':
	main()
