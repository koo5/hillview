"""Standalone SQL from independently verified detection before/after JSON texts."""
import hashlib
import json
import os

from photo_size_sql import block, literal


def value(item):
	if item is None:
		return 'NULL'
	if type(item) is bool:
		return 'TRUE' if item else 'FALSE'
	return literal(str(item))


def render(rows, *, source, blur_confidence):
	serialized = json.dumps({'rows': rows, 'blur_confidence': blur_confidence},
	                        ensure_ascii=False, sort_keys=True, allow_nan=False)
	digest = hashlib.sha256(serialized.encode()).hexdigest()
	table = 'detections_fix_' + digest[:16]
	backup = f'public."{table}"'
	count = len(rows)
	source_comment = '\n'.join('-- Source: ' + line for line in source.splitlines())
	header = f'''-- Detections format backfill: persist the existing reader verdicts.
{source_comment}
-- Planned photos: {count}; blur confidence: {blur_confidence:g}.
-- Before/after plan SHA-256: {digest}
-- Backup table: {backup} (retained after commit).
-- Run with psql -v ON_ERROR_STOP=1 -f <this-file> using your usual connection.
-- Only detected_objects changes. No boxes, pixels, dimensions or existing flags are changed.
-- Apply is one-shot; an existing backup table is never overwritten.
'''
	apply = header + f'''BEGIN;
CREATE TABLE {backup} (
    id text PRIMARY KEY, before_text text NOT NULL, after_text text NOT NULL,
    file_md5 text, filename text, processed_at timestamptz,
    processing_status text, deleted boolean,
    backed_up_at timestamptz NOT NULL DEFAULT now()
);
CREATE TEMP TABLE detections_fix_plan (
    id text PRIMARY KEY, before_text text NOT NULL, after_text text NOT NULL,
    file_md5 text, filename text, processed_at timestamptz,
    processing_status text, deleted boolean
) ON COMMIT DROP;
'''
	parts = [apply]
	for start in range(0, count, 100):
		values = []
		for row in rows[start:start + 100]:
			context = row['context']
			items = [row['id'], row['before_text'], row['after_text'],
			         *[context[k] for k in ('file_md5', 'filename', 'processed_at', 'processing_status', 'deleted')]]
			values.append('(' + ','.join(value(item) for item in items) + ')')
		parts.append('INSERT INTO pg_temp.detections_fix_plan VALUES\n' + ',\n'.join(values) + ';\n')
	parts.append(block(f'''DECLARE
    locked integer;
    changed integer;
    bad integer;
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name='photos' AND column_name='detected_objects')
        IS DISTINCT FROM 'json' THEN
        RAISE EXCEPTION 'Expected public.photos.detected_objects to be json';
    END IF;
    PERFORM p.id FROM public.photos p JOIN pg_temp.detections_fix_plan q ON q.id=p.id
        ORDER BY p.id FOR UPDATE OF p;
    GET DIAGNOSTICS locked = ROW_COUNT;
    IF locked <> {count} THEN
        RAISE EXCEPTION 'Expected {count} planned photos, found %; nothing applied', locked;
    END IF;
    IF EXISTS (SELECT 1 FROM public.photos p JOIN pg_temp.detections_fix_plan q ON q.id=p.id
        WHERE ROW(p.file_md5,p.filename,p.processed_at,p.processing_status,p.deleted)
            IS DISTINCT FROM ROW(q.file_md5,q.filename,q.processed_at,q.processing_status,q.deleted)
        OR (p.detected_objects::text IS DISTINCT FROM q.before_text
            AND p.detected_objects::text IS DISTINCT FROM q.after_text)) THEN
        RAISE EXCEPTION 'Photo identity or detections changed since export; nothing applied';
    END IF;
    INSERT INTO {backup} (id,before_text,after_text,file_md5,filename,processed_at,processing_status,deleted)
        SELECT q.* FROM pg_temp.detections_fix_plan q JOIN public.photos p ON p.id=q.id
        WHERE p.detected_objects::text IS NOT DISTINCT FROM q.before_text;
    WITH updated AS (
        UPDATE public.photos p SET detected_objects=b.after_text::json
        FROM {backup} b WHERE p.id=b.id AND p.detected_objects::text IS NOT DISTINCT FROM b.before_text
        RETURNING p.id,p.detected_objects::text AS actual,b.after_text AS expected
    ) SELECT count(*),count(*) FILTER (WHERE actual IS DISTINCT FROM expected)
        INTO changed,bad FROM updated;
    IF bad <> 0 OR changed <> (SELECT count(*) FROM {backup}) THEN
        RAISE EXCEPTION 'Detection write verification failed; nothing applied';
    END IF;
    IF EXISTS (SELECT 1 FROM public.photos p JOIN pg_temp.detections_fix_plan q ON q.id=p.id
        WHERE p.detected_objects::text IS DISTINCT FROM q.after_text) THEN
        RAISE EXCEPTION 'Final detection verification failed; nothing applied';
    END IF;
    RAISE NOTICE 'Migrated % photos; % already matching. Backup: {backup}', changed, {count}-changed;
END;'''))
	parts.append(f'SELECT count(*) AS backed_up_photos FROM {backup};\nCOMMIT;\n')
	result = {'apply': ''.join(parts), 'backup_table': 'public.' + table, 'plan_sha256': digest}
	for restoring in (False, True):
		operation = 'restore' if restoring else 'verify'
		body = f'''DECLARE
    locked integer;
    changed integer;
    bad integer;
BEGIN
    PERFORM p.id FROM public.photos p JOIN {backup} b ON b.id=p.id
        ORDER BY p.id FOR {'UPDATE' if restoring else 'SHARE'} OF p;
    GET DIAGNOSTICS locked = ROW_COUNT;
    IF locked <> (SELECT count(*) FROM {backup}) THEN
        RAISE EXCEPTION 'A backed-up photo is missing; nothing applied';
    END IF;
    IF EXISTS (SELECT 1 FROM public.photos p JOIN {backup} b ON b.id=p.id
        WHERE ROW(p.file_md5,p.filename,p.processed_at,p.processing_status,p.deleted)
            IS DISTINCT FROM ROW(b.file_md5,b.filename,b.processed_at,b.processing_status,b.deleted)
        OR (p.detected_objects::text IS DISTINCT FROM b.after_text
            {'AND p.detected_objects::text IS DISTINCT FROM b.before_text' if restoring else ''})) THEN
        RAISE EXCEPTION 'Later edits or photo identity conflict with detection backup; nothing applied';
    END IF;
'''
		if restoring:
			body += f'''    WITH updated AS (
        UPDATE public.photos p SET detected_objects=b.before_text::json
        FROM {backup} b WHERE p.id=b.id AND p.detected_objects::text IS NOT DISTINCT FROM b.after_text
        RETURNING p.id,p.detected_objects::text AS actual,b.before_text AS expected
    ) SELECT count(*),count(*) FILTER (WHERE actual IS DISTINCT FROM expected)
        INTO changed,bad FROM updated;
    IF bad <> 0 THEN
        RAISE EXCEPTION 'Restore write verification failed; nothing applied';
    END IF;
    IF EXISTS (SELECT 1 FROM public.photos p JOIN {backup} b ON b.id=p.id
        WHERE p.detected_objects::text IS DISTINCT FROM b.before_text) THEN
        RAISE EXCEPTION 'Final restore verification failed; nothing applied';
    END IF;
'''
		body += f'''    RAISE NOTICE '{operation}: % backed-up photos checked', locked;
END;'''
		result[operation] = header + f'-- {operation.upper()} using the retained backup.\nBEGIN;\n' + block(body) + 'COMMIT;\n'
	return result


def write_export(rows, *, source, blur_confidence, output, summary):
	paths = {'apply': output, 'verify': output.with_suffix('.verify.sql'),
	         'restore': output.with_suffix('.restore.sql'), 'evidence': output.with_suffix('.evidence.json')}
	if len(set(paths.values())) != len(paths) or any(p.exists() or p.is_symlink() for p in paths.values()):
		raise ValueError('SQL output files must be distinct and new')
	scripts = render(rows, source=source, blur_confidence=blur_confidence)
	output.parent.mkdir(parents=True, exist_ok=True)
	for name, path in paths.items():
		content = json.dumps({**summary, 'photo_ids': [row['id'] for row in rows], 'backup_table': scripts['backup_table'],
		                      'plan_sha256': scripts['plan_sha256']}, indent=2, sort_keys=True) + '\n' if name == 'evidence' else scripts[name]
		fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, 'w') as stream:
			stream.write(content)
	return {'files': {key: str(path) for key, path in paths.items()},
	        'backup_table': scripts['backup_table'], 'plan_sha256': scripts['plan_sha256'], 'photos': len(rows)}
