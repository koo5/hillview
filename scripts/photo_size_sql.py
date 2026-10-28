"""Self-contained PostgreSQL repair/verify/restore scripts for reviewed size plans."""
import hashlib


def literal(value):
	return "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"


def block(body):
	tag = '$size_fix_' + hashlib.sha256(body.encode()).hexdigest()[:16] + '$'
	while tag in body:
		tag = tag[:-1] + '_$'
	return f'DO {tag}\n{body}\n{tag};\n'


def bundle(plan_json, photos_json, count, checks_summary):
	digest = hashlib.sha256(plan_json.encode()).hexdigest()
	table = 'photo_size_fix_' + digest[:16]
	qualified = f'public."{table}"'
	header = f'''-- Photo dimensions: match the existing uploaded artifacts.
-- Reviewed plan SHA-256: {digest}
-- Selected photos: {count}. {checks_summary}
-- Run with psql -v ON_ERROR_STOP=1 -f <this-file> using your usual DB connection.
-- One transaction; a conflict aborts all changes. No image/detection writes.
-- Backup table: {qualified} (retained after commit).
-- Apply is one-shot: an existing backup table causes failure, never overwrite.
'''
	apply = header + f'''BEGIN;
CREATE TABLE {qualified} (
    id text PRIMARY KEY,
    before_width integer, before_height integer, before_sizes_text text,
    after_width integer, after_height integer, after_sizes_text text,
    file_md5 text, filename text, processed_at timestamptz,
    processing_status text, deleted boolean,
    reviewed_photo jsonb NOT NULL,
    backed_up_at timestamptz NOT NULL DEFAULT now()
);
'''
	apply += block(f'''DECLARE
    plan jsonb := {literal(photos_json)}::jsonb;
    photo jsonb;
    change jsonb;
    r record;
    written record;
    full_meta jsonb;
    basis jsonb;
    sizes_after jsonb;
    sizes_after_text text;
    variant text;
    current_pair jsonb;
    target_width integer;
    target_height integer;
    locked integer;
    changed integer := 0;
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name='photos' AND column_name='sizes')
        IS DISTINCT FROM 'json' THEN
        RAISE EXCEPTION 'Expected public.photos.sizes to be json';
    END IF;
    PERFORM p.id FROM public.photos p
        WHERE p.id IN (SELECT value->>'id' FROM jsonb_array_elements(plan))
        ORDER BY p.id FOR UPDATE;
    GET DIAGNOSTICS locked = ROW_COUNT;
    IF locked <> {count} THEN
        RAISE EXCEPTION 'Expected {count} reviewed photos, found %; nothing applied', locked;
    END IF;
    FOR photo IN SELECT value FROM jsonb_array_elements(plan) ORDER BY value->>'id' LOOP
        SELECT * INTO STRICT r FROM public.photos WHERE id=photo->>'id';
        IF r.processing_status IS DISTINCT FROM 'completed'
            OR r.deleted IS DISTINCT FROM (photo->>'deleted')::boolean
            OR r.processed_at IS DISTINCT FROM (photo->>'processed_at')::timestamptz THEN
            RAISE EXCEPTION '%: processing identity/status changed', r.id;
        END IF;
        IF photo#>>'{{original_source_evidence,matches_photo_file_md5}}' = 'true'
            AND r.file_md5 IS DISTINCT FROM photo#>>'{{original_source_evidence,file_md5}}' THEN
            RAISE EXCEPTION '%: source MD5 changed', r.id;
        END IF;
        IF jsonb_build_array(r.width,r.height) IS DISTINCT FROM photo->'photo_dimensions'
            AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(photo->'changes') c
                WHERE c->>'path'='photos.width/height'
                AND c->'after'=jsonb_build_array(r.width,r.height)) THEN
            RAISE EXCEPTION '%: photo dimensions changed since review', r.id;
        END IF;
        full_meta := r.sizes::jsonb->'full';
        IF jsonb_build_array(full_meta->'width',full_meta->'height') IS DISTINCT FROM photo->'full_dimensions'
            OR full_meta->>'url' IS DISTINCT FROM photo->>'full_url' THEN
            RAISE EXCEPTION '%: full rendition changed', r.id;
        END IF;
        target_width := r.width;
        target_height := r.height;
        sizes_after := r.sizes::jsonb;
        FOR change IN SELECT value FROM jsonb_array_elements(photo->'changes') LOOP
            IF change->>'path'='photos.width/height' THEN
                current_pair := jsonb_build_array(target_width,target_height);
                IF change#>>'{{artifact,kind}}'='dzi' THEN
                    basis := full_meta->'pyramid';
                    IF basis->>'dzi_url' IS DISTINCT FROM change#>>'{{artifact,url}}' THEN
                        RAISE EXCEPTION '%: DZI URL changed', r.id;
                    END IF;
                ELSE
                    basis := full_meta;
                    IF basis->>'url' IS DISTINCT FROM change#>>'{{artifact,url}}' THEN
                        RAISE EXCEPTION '%: full URL changed', r.id;
                    END IF;
                END IF;
                IF jsonb_build_array(basis->'width',basis->'height') IS DISTINCT FROM change->'after' THEN
                    RAISE EXCEPTION '%: dimension artifact basis changed', r.id;
                END IF;
            ELSE
                variant := split_part(change->>'path','.',2);
                basis := sizes_after->variant;
                current_pair := jsonb_build_array(basis->'width',basis->'height');
                IF basis->>'url' IS DISTINCT FROM change#>>'{{artifact,url}}' THEN
                    RAISE EXCEPTION '%: rendition URL changed', r.id;
                END IF;
            END IF;
            IF current_pair = change->'after' THEN
                CONTINUE;
            END IF;
            IF current_pair IS DISTINCT FROM change->'before' THEN
                RAISE EXCEPTION '%: % changed since review', r.id, change->>'path';
            END IF;
            IF change->>'path'='photos.width/height' THEN
                target_width := (change#>>'{{after,0}}')::integer;
                target_height := (change#>>'{{after,1}}')::integer;
            ELSE
                sizes_after := jsonb_set(sizes_after, ARRAY[variant,'width'], change#>'{{after,0}}', false);
                sizes_after := jsonb_set(sizes_after, ARRAY[variant,'height'], change#>'{{after,1}}', false);
            END IF;
        END LOOP;
        -- Preserve the exact raw JSON text when only photo dimensions change.
        sizes_after_text := CASE WHEN sizes_after IS DISTINCT FROM r.sizes::jsonb
            THEN sizes_after::text ELSE r.sizes::text END;
        IF ROW(target_width,target_height,sizes_after_text)
            IS NOT DISTINCT FROM ROW(r.width,r.height,r.sizes::text) THEN
            CONTINUE;
        END IF;
        INSERT INTO {qualified} (id,before_width,before_height,before_sizes_text,
            after_width,after_height,after_sizes_text,file_md5,filename,processed_at,
            processing_status,deleted,reviewed_photo)
        VALUES (r.id,r.width,r.height,r.sizes::text,target_width,target_height,sizes_after_text,
            r.file_md5,r.filename,r.processed_at,r.processing_status,r.deleted,photo);
        UPDATE public.photos SET width=target_width,height=target_height,sizes=sizes_after_text::json
            WHERE id=r.id RETURNING width,height,sizes::text AS sizes_text INTO STRICT written;
        IF ROW(written.width,written.height,written.sizes_text)
            IS DISTINCT FROM ROW(target_width,target_height,sizes_after_text) THEN
            RAISE EXCEPTION '%: write verification failed', r.id;
        END IF;
        changed := changed + 1;
    END LOOP;
    RAISE NOTICE 'Repaired % photos; % already matching. Backup: {qualified}', changed, {count}-changed;
END;''')
	apply += f'SELECT count(*) AS backed_up_photos FROM {qualified};\nCOMMIT;\n'
	companions = {}
	for restoring in (False, True):
		operation = 'restore' if restoring else 'verify'
		body = f'''DECLARE
    b record;
    r record;
    written record;
    checked integer := 0;
BEGIN
    FOR b IN SELECT * FROM {qualified} ORDER BY id LOOP
        SELECT * INTO r FROM public.photos WHERE id=b.id {'FOR UPDATE' if restoring else 'FOR SHARE'};
        IF NOT FOUND THEN
            RAISE EXCEPTION '%: photo missing', b.id;
        END IF;
        IF ROW(r.file_md5,r.filename,r.processed_at,r.processing_status,r.deleted)
            IS DISTINCT FROM ROW(b.file_md5,b.filename,b.processed_at,b.processing_status,b.deleted) THEN
            RAISE EXCEPTION '%: photo identity/status changed', b.id;
        END IF;
        IF ROW(r.width,r.height,r.sizes::text)
            IS NOT DISTINCT FROM ROW(b.after_width,b.after_height,b.after_sizes_text) THEN
'''
		if restoring:
			body += '''            UPDATE public.photos SET width=b.before_width,height=b.before_height,sizes=b.before_sizes_text::json
                WHERE id=b.id RETURNING width,height,sizes::text AS sizes_text INTO STRICT written;
            IF ROW(written.width,written.height,written.sizes_text)
                IS DISTINCT FROM ROW(b.before_width,b.before_height,b.before_sizes_text) THEN
                RAISE EXCEPTION '%: restore verification failed', b.id;
            END IF;
'''
		body += '''            checked := checked + 1;
'''
		if restoring:
			body += '''        ELSIF ROW(r.width,r.height,r.sizes::text)
            IS NOT DISTINCT FROM ROW(b.before_width,b.before_height,b.before_sizes_text) THEN
            checked := checked + 1; -- Already restored.
'''
		body += f'''        ELSE
            RAISE EXCEPTION '%: metadata differs from backup; nothing applied', b.id;
        END IF;
    END LOOP;
    RAISE NOTICE '{operation}: % backed-up photos checked', checked;
END;'''
		companions[operation] = header + f'-- {operation.upper()} using the retained backup table.\nBEGIN;\n' + block(body) + 'COMMIT;\n'
	return {'apply': apply, **companions, 'backup_table': table, 'plan_sha256': digest}
