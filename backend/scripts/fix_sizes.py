#!/usr/bin/env python3
"""
Utility script to fix mismatched photo dimensions in the database.
Reads a JSON export of photos and generates SQL UPDATE statements.

Usage: python fix_sizes.py photos_export.json > fix_updates.sql
"""

import sys
import json
import re

# Regex pattern to validate UUID format
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)


def validate_uuid(value: str) -> bool:
    """Validate that a string is a proper UUID format."""
    return bool(UUID_PATTERN.match(value))


def escape_sql_string(value: str) -> str:
    """Escape a string for safe inclusion in PostgreSQL SQL statements."""
    # PostgreSQL escapes single quotes by doubling them
    return value.replace("'", "''")


photos = json.loads(open(sys.argv[1], 'r').read())
fixed_count = 0
for photo in photos:
	sizes = photo.get('sizes')
	if sizes == None:
		#print(f"Photo {photo['id']} has no sizes, skipping")
		#print(json.dumps(photo, indent=2))
		continue

	s320 = sizes.get('320')
	if s320 == None:
		print(f"Photo {photo['id']} missing size 320, skipping")
		#print(json.dumps(photo, indent=2))
		continue

	sfull = sizes.get('full')
	if sfull == None:
		print(f"Photo {photo['id']} missing size full, skipping")
		#print(json.dumps(photo, indent=2))
		continue

	if s320['width'] > s320['height']:
		if sfull['width'] < sfull['height']:
			#print(f"Photo {photo['id']} has mismatched sizes, fixing full size")
			#fixed_count += 1
			#print(json.dumps(photo['record_created_ts'], indent=2))
			#print(json.dumps(photo, indent=2))
			fixed_sizes = sizes.copy()
			h = sfull['height']
			w = sfull['width']
			fixed_sizes['full']['width'] = h
			fixed_sizes['full']['height'] = w

			# Security: Validate photo ID is a proper UUID to prevent SQL injection
			photo_id = photo.get('id', '')
			if not validate_uuid(photo_id):
				print(f"-- SKIPPED: Invalid UUID format for photo id: {repr(photo_id)[:50]}", file=sys.stderr)
				continue

			# Security: Validate dimensions are integers
			if not isinstance(w, int) or not isinstance(h, int):
				print(f"-- SKIPPED: Invalid dimensions for photo {photo_id}", file=sys.stderr)
				continue

			# Security: Escape the JSON string properly for PostgreSQL
			escaped_json = escape_sql_string(json.dumps(fixed_sizes))

			print(f"UPDATE photos SET width = {w}, height = {h}, sizes = '{escaped_json}' WHERE id = '{photo_id}';")
			fixed_count += 1
