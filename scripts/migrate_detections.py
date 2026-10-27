#!/usr/bin/env python3
"""Backfill explicit blur flags, with durable backups and guarded restoration.

No implicit DB target or dotenv loading. `migrate` and `restore` default to dry
run. Apply requires a private backup directory; resume rescans the original ID
range, skipping already-normalized rows. A batch's raw before/after JSON texts
are fsynced before UPDATE, including batches whose transaction later rolls back.
Only detected_objects is updated. Reader fallbacks remain until prod rollout.
"""

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from common.detections import (  # noqa: E402
	BLUR_CONFIDENCE, normalize_detections, verify_detection_migration,
)

VERSION = 1
SELECT_BATCH = """
SELECT id, detected_objects::text AS before_text FROM public.photos
WHERE ($1::text IS NULL OR id > $1) AND id <= $2
ORDER BY id LIMIT $3
"""
UPDATE_BATCH = """
UPDATE public.photos AS p SET detected_objects = b.after_text::json
FROM jsonb_to_recordset($1::jsonb)
     AS b(id text, before_text text, after_text text)
WHERE p.id = b.id AND p.detected_objects::text IS NOT DISTINCT FROM b.before_text
RETURNING p.id, p.detected_objects::text AS after_text
"""


def now():
	return datetime.now(timezone.utc).isoformat()


def encode(value):
	return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def sync_directory(path):
	fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
	try:
		os.fsync(fd)
	finally:
		os.close(fd)


def save_document(path, document):
	"""Exclusive, checksummed, durable file. Failure must precede DB writes."""
	payload = encode(document)
	envelope = {'sha256': hashlib.sha256(payload.encode()).hexdigest(), 'payload': document}
	fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
	with os.fdopen(fd, 'w') as stream:
		stream.write(encode(envelope) + '\n')
		stream.flush()
		os.fsync(stream.fileno())
	sync_directory(path.parent)


def read_document(path):
	envelope = json.loads(path.read_text())
	if hashlib.sha256(encode(envelope['payload']).encode()).hexdigest() != envelope['sha256']:
		raise ValueError(f'Backup checksum mismatch: {path.name}')
	return envelope['payload']


@contextmanager
def backup_lock(directory):
	fd = os.open(directory / '.lock', os.O_RDWR | os.O_CREAT, 0o600)
	try:
		fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
		yield
	finally:
		os.close(fd)


def load_backups(directory):
	"""Deduplicate backups of retried transactions; refuse ambiguous histories."""
	rows = {}
	for path in sorted(directory.glob('batch-*.json')):
		batch = read_document(path)
		if batch['version'] != VERSION:
			raise ValueError('Unsupported backup version')
		for row in batch['rows']:
			if row['id'] in rows and rows[row['id']] != row:
				raise ValueError(f'Multiple different backups for photo {row["id"]}; manual review required')
			rows[row['id']] = row
	return list(rows.values())


async def identity(conn):
	return dict(await conn.fetchrow("""
		SELECT current_database() AS database, inet_server_addr()::text AS server_address,
		       inet_server_port() AS server_port,
		       (SELECT data_type FROM information_schema.columns
		        WHERE table_schema='public' AND table_name='photos'
		          AND column_name='detected_objects') AS column_type
	"""))


async def update_rows(conn, rows):
	updated = await conn.fetch(UPDATE_BATCH, encode(rows))
	expected = {row['id']: row['after_text'] for row in rows}
	if {row['id']: row['after_text'] for row in updated} != expected:
		raise ValueError('Batch write verification failed; transaction will roll back')


def plan_row(row):
	before = json.loads(row['before_text']) if row['before_text'] is not None else None
	try:
		after = normalize_detections(before)
		verify_detection_migration(before, after)
	except ValueError as exc:
		raise ValueError(f'Photo {row["id"]}: {exc}') from exc
	counts = Counter()
	if after == before:
		return None, counts
	for old, new in zip(before['objects'], after['objects']):
		if 'blurred' not in old:
			counts['objects_added'] += 1
			counts['blurred_true' if new['blurred'] else 'blurred_false'] += 1
			counts['legacy_no_confidence' if old.get('confidence') is None else 'legacy_confidence'] += 1
	return {'id': row['id'], 'before_text': row['before_text'], 'after_text': encode(after)}, counts


async def migrate(conn, *, apply=False, backup_dir=None, resume=False, source,
                  batch_size=500, after_id=None, through_id=None):
	db_identity = await identity(conn)
	if db_identity['column_type'] != 'json':
		raise ValueError('Expected public.photos.detected_objects to be json')
	if resume:
		manifest = read_document(backup_dir / 'manifest.json')
		previous = {row['id']: row for row in load_backups(backup_dir)}
		if manifest['version'] != VERSION or manifest['blur_confidence'] != BLUR_CONFIDENCE:
			raise ValueError('Backup version/threshold differs from this migration')
		if manifest['database'] != db_identity:
			raise ValueError('Backup database identity differs from target')
		if after_id != manifest['after_id'] or (through_id is not None and through_id != manifest['through_id']):
			raise ValueError('Resume must use the original ID range')
		through_id = manifest['through_id']
	else:
		previous = {}
		if through_id is None:
			through_id = await conn.fetchval('SELECT max(id) FROM public.photos')
		if apply:
			save_document(backup_dir / 'manifest.json', {
				'version': VERSION, 'created_at': now(), 'source': source,
				'database': db_identity, 'blur_confidence': BLUR_CONFIDENCE,
				'after_id': after_id, 'through_id': through_id,
			})
	counts = Counter()
	cursor = after_id
	while through_id is not None:
		async with conn.transaction(readonly=not apply):
			rows = await conn.fetch(SELECT_BATCH + (' FOR UPDATE' if apply else ''), cursor, through_id, batch_size)
			if not rows:
				break
			planned, additions = [], Counter()
			for row in rows:
				change, row_counts = plan_row(row)
				if change is not None:
					if change['id'] in previous and previous[change['id']] != change:
						raise ValueError(f'Photo {change["id"]} changed since its backup; use a new backup directory')
					planned.append(change)
					additions.update(row_counts)
			if planned and apply:
				save_document(backup_dir / f'batch-{time.time_ns()}-{uuid.uuid4().hex}.json', {
					'version': VERSION, 'created_at': now(), 'rows': planned,
				})
				await update_rows(conn, planned)
		# Advance/report only after commit. An interrupted run can be resumed by
		# rescanning: explicit flags make completed batches no-ops.
		cursor = rows[-1]['id']
		counts.update(additions)
		counts['photos_scanned'] += len(rows)
		counts['photos_changed' if apply else 'photos_would_change'] += len(planned)
		counts['photos_verified'] += len(planned)
		counts['batches_scanned'] += 1
		if planned and (counts['batches_scanned'] == 1 or counts['batches_scanned'] % 10 == 0):
			print(encode({'last_id': cursor, **counts}), file=sys.stderr, flush=True)
	return {'command': 'migrate', 'apply': apply, 'source': source,
	        'after_id': after_id, 'through_id': through_id, 'last_id': cursor, **counts}


async def restore_or_verify(conn, *, backup_dir, command, apply=False, batch_size=500):
	manifest = read_document(backup_dir / 'manifest.json')
	if manifest['version'] != VERSION or manifest['database'] != await identity(conn):
		raise ValueError('Backup version/database identity differs from target')
	backups = load_backups(backup_dir)
	counts = Counter()
	conflicts = []
	for start in range(0, len(backups), batch_size):
		batch = backups[start:start + batch_size]
		async with conn.transaction(readonly=not apply):
			current = await conn.fetch(
				'SELECT id, detected_objects::text AS value FROM public.photos WHERE id = ANY($1::text[])'
				+ (' ORDER BY id FOR UPDATE' if apply else ''), [row['id'] for row in batch])
			values = {row['id']: row['value'] for row in current}
			changes, batch_conflicts = [], []
			for row in batch:
				if row['id'] not in values:
					batch_conflicts.append(row['id'])
				elif values[row['id']] == row['after_text']:
					counts['at_migrated_value'] += 1
					changes.append({'id': row['id'], 'before_text': row['after_text'], 'after_text': row['before_text']})
				elif values[row['id']] == row['before_text']:
					counts['at_original_value'] += 1
				else:
					batch_conflicts.append(row['id'])
			if batch_conflicts and apply:
				raise ValueError(f'Restore refused later edits/missing rows: {batch_conflicts[:10]}')
			conflicts.extend(batch_conflicts)
			if changes and command == 'restore':
				if apply:
					await update_rows(conn, changes)
				counts['photos_restored' if apply else 'photos_would_restore'] += len(changes)
	return {'command': command, 'apply': apply, 'backup_photos': len(backups),
	        'conflicts': len(conflicts), 'conflict_examples': conflicts[:10], **counts}


async def run(args):
	import asyncpg

	url = os.environ[args.database_url_env].replace('postgresql+asyncpg://', 'postgresql://', 1)
	conn = await asyncpg.connect(url, server_settings={
		'default_transaction_read_only': 'off' if args.apply else 'on',
		'application_name': 'detections-migration', 'lock_timeout': '5s', 'statement_timeout': '60s',
	})
	try:
		if args.command == 'migrate':
			kwargs = {key: getattr(args, key) for key in
			          ('apply', 'backup_dir', 'resume', 'source', 'batch_size', 'after_id', 'through_id')}
			if args.apply:
				with backup_lock(args.backup_dir):
					return await migrate(conn, **kwargs)
			# A dry run is one consistent read-only snapshot; apply commits per batch.
			async with conn.transaction(isolation='repeatable_read', readonly=True):
				return await migrate(conn, **kwargs)
		with backup_lock(args.backup_dir):
			return await restore_or_verify(conn, backup_dir=args.backup_dir, command=args.command,
			                               apply=args.apply, batch_size=args.batch_size)
	finally:
		await conn.close()


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	commands = parser.add_subparsers(dest='command', required=True)
	for name in ('migrate', 'restore', 'verify'):
		sub = commands.add_parser(name)
		sub.add_argument('--database-url-env', required=True)
		sub.add_argument('--batch-size', type=int, default=500)
		mode = sub.add_mutually_exclusive_group()
		mode.add_argument('--dry-run', action='store_true', help='Default: read only')
		if name != 'verify':
			mode.add_argument('--apply', action='store_true')
		sub.set_defaults(apply=False)
		sub.add_argument('--backup-dir', type=Path, required=name != 'migrate')
		if name == 'migrate':
			sub.add_argument('--source', required=True)
			sub.add_argument('--resume', action='store_true', help='Reuse backup directory; rescan original range')
			sub.add_argument('--after-id')
			sub.add_argument('--through-id')
	args = parser.parse_args()
	if not os.environ.get(args.database_url_env):
		parser.error('Specified database URL environment variable is empty')
	if not 1 <= args.batch_size <= 5000:
		parser.error('--batch-size must be in [1, 5000]')
	if args.command == 'migrate':
		if args.apply and args.backup_dir is None:
			parser.error('--apply requires --backup-dir')
		if args.resume and not args.apply:
			parser.error('--resume requires --apply')
		if args.apply and not args.resume:
			args.backup_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
			sync_directory(args.backup_dir.parent)
	try:
		result = asyncio.run(run(args))
	except (ValueError, OSError) as exc:
		parser.exit(2, f'{exc}\n')
	print(json.dumps(result, indent=2, sort_keys=True))
	if result.get('conflicts') or (args.command == 'verify' and result.get('at_original_value')):
		raise SystemExit(2)


if __name__ == '__main__':
	main()
