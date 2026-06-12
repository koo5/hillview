#!/usr/bin/env python3
"""
Rewrite URLs in the photos.sizes JSON field, replacing an old base URL
prefix with a new one in every size entry.

Usage (from backend/ directory, with DATABASE_URL set):
	# Dry run - print what would change
	python scripts/rewrite_sizes_urls.py

	# Apply the changes
	python scripts/rewrite_sizes_urls.py --apply

	# Custom prefixes
	python scripts/rewrite_sizes_urls.py --old https://10.0.0.24:9999/ --new https://hillview.jj.internal/ --apply

Environment:
	DATABASE_URL - PostgreSQL connection string (postgresql+asyncpg://...)
"""

import argparse
import asyncio
import os
import sys

# Make the common package importable when run from backend/ or scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from common.database import SessionLocal
from common.models import Photo

# Note: stored URLs use http://, not https://
DEFAULT_OLD_PREFIX = 'http://10.0.0.24:9999/pics2/'
DEFAULT_NEW_PREFIX = 'https://hillview.jj.internal/pics2/'

BATCH_SIZE = 500


def rewrite_value(value, old_prefix: str, new_prefix: str, changes: list):
	"""Recursively rewrite string values starting with old_prefix.

	Returns the (possibly new) value. Appends (old, new) pairs to changes.
	"""
	if isinstance(value, str):
		if value.startswith(old_prefix):
			new_value = new_prefix + value[len(old_prefix):]
			changes.append((value, new_value))
			return new_value
		return value
	if isinstance(value, dict):
		return {k: rewrite_value(v, old_prefix, new_prefix, changes) for k, v in value.items()}
	if isinstance(value, list):
		return [rewrite_value(v, old_prefix, new_prefix, changes) for v in value]
	return value


async def main():
	parser = argparse.ArgumentParser(description='Rewrite URL prefixes in photos.sizes')
	parser.add_argument('--old', default=DEFAULT_OLD_PREFIX, help=f'Old URL prefix (default: {DEFAULT_OLD_PREFIX})')
	parser.add_argument('--new', default=DEFAULT_NEW_PREFIX, help=f'New URL prefix (default: {DEFAULT_NEW_PREFIX})')
	parser.add_argument('--apply', action='store_true', help='Actually write changes (default is dry run)')
	args = parser.parse_args()

	if SessionLocal is None:
		print('Database not initialized (ALEMBIC_SYNC_MODE is set?)', file=sys.stderr)
		sys.exit(1)

	total = 0
	updated = 0
	url_rewrites = 0

	async with SessionLocal() as session:
		result = await session.stream_scalars(
			select(Photo).where(Photo.sizes.isnot(None)).execution_options(yield_per=BATCH_SIZE)
		)
		async for photo in result:
			total += 1
			changes = []
			new_sizes = rewrite_value(photo.sizes, args.old, args.new, changes)
			if not changes:
				continue

			updated += 1
			url_rewrites += len(changes)
			print(f'Photo {photo.id}:')
			for old_url, new_url in changes:
				print(f'  {old_url}')
				print(f'    -> {new_url}')

			if args.apply:
				photo.sizes = new_sizes
				flag_modified(photo, 'sizes')

		if args.apply:
			await session.commit()

	print()
	print(f'Scanned {total} photos with sizes, {updated} matched ({url_rewrites} URLs rewritten)')
	if not args.apply:
		print('Dry run - no changes written. Re-run with --apply to update the database.')


if __name__ == '__main__':
	asyncio.run(main())
