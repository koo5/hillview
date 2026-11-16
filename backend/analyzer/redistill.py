"""Finite database-backed distillation pass. No LLM calls or provider credentials."""
import json
import math
from collections import Counter
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, select, update, or_, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import load_only

from analyze_photo import build_schema, validate_analysis
from aaa_source import AaaSource, EXTRA_DB_KEYS, backfill_image_hash
from response_store import load_photo_sessions, has_responses
from common.artifact_identity import selected_image, session_matches_image
from distill import acquire_file_lock, release_file_lock, lock_path_for, load_sessions, save_sessions, distill_sessions


def external_document(record, db_document):
    doc = db_document(record['analysis'])
    # Shape v2 adds structured context to v1 sky-only null distances. Rubric
    # meanings and closest mapping are explicit, never inferred from model ID.
    doc.update({key: record['analysis'][key] for key in EXTRA_DB_KEYS if key in record['analysis']})
    doc['schema_version'] = 2
    doc['analysis_source'] = {
        'source': record.get('source','aaa'), 'adapter_version': record['adapter_version'],
        'fingerprint': record['source_fingerprint'], 'closest_policy': record['closest_policy'],
        'rubric': record['raw'].get('by', {}).get('rubric'),
        'model': (record['raw'].get('by') or {}).get('model'),
        'checkout_commit': record.get('provenance', {}).get('checkout_commit'),
        'review_status': record.get('provenance', {}).get('supervision', {}).get('photo_review_status'),
        'warnings': record.get('warnings', []),
        'image_content_sha256': record.get('image_content_sha256'),
    }
    return doc


def complete_native(answer, keys):
    if answer is None or not all(k in answer and answer[k] is not None for k in keys):
        return False
    properties = build_schema(distances=False)['properties']
    for key in keys:
        value = answer[key]
        if key in ('closest_object_distance', 'farthest_object_distance'):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                return False
        elif key == 'features':
            if not isinstance(value, list) or any(not isinstance(f, str) or f not in properties['features']['properties'] for f in value):
                return False
        elif validate_analysis(value, properties[key]):
            return False
    return answer['closest_object_distance'] <= answer['farthest_object_distance']


def disk_document(photo, datadir, source=None, *, persist=True, verify_images=False, fetch=None):
    """Called under the photo history lock; never calls a model or writes the DB."""
    from analyzer import db_document, DB_ANALYSIS_KEYS, get_image_url, json_path_for, TRUSTED_MODELS
    from aaa_source import normalize
    from distill import session_fingerprint
    pid=str(photo.id)
    record=source.resolve(pid,file_md5=photo.file_md5,image_url=get_image_url(photo),
                          image_sha256=selected_image(photo).get('sha256'),
                          artifact_version=selected_image(photo).get('artifact_version')) if source else None
    if record is not None:
        cache=source.output_dir/'records'/f'{pid}.json'
        history=load_sessions(cache)
        if not history:history=load_sessions(datadir/'meta/aaa'/f'{pid}.json')
        previous=next((r for r in reversed(history) if r.get('image_hash') and r.get('image_url')==record['image_url']),None)
        if verify_images:backfill_image_hash(record,previous,fetch)
        elif previous:
            record['image_hash']=previous['image_hash'];record['image_bytes']=previous['image_bytes']
        if persist or verify_images:
            if record not in history:
                history.append(record);save_sessions(cache,history,durable=bool(record.get('image_hash')))
            elif not cache.exists():save_sessions(cache,history,durable=bool(record.get('image_hash')))
        return external_document(record,db_document),record.get('source','aaa'),record
    sessions=[s for s in load_photo_sessions(datadir,photo) if session_matches_image(s,photo)]
    for session in sorted(sessions,key=lambda s:s.get('metadata',{}).get('timestamp',''),reverse=True):
        if session.get('haiku_label') and session.get('metadata',{}).get('model') in TRUSTED_MODELS and not session.get('result',{}).get('parse_error',True):
            if not selected_image(photo).get('sha256') and session.get('metadata',{}).get('image_url') != get_image_url(photo):continue
            row=session['haiku_label']
            if 'skip' in row:continue
            record={'source':'haiku_native','adapter_version':2,'raw':row,
                'image_content_sha256':selected_image(photo).get('sha256'),
                'analysis':normalize(row,closest_policy='subject'),'source_fingerprint':session_fingerprint(session),
                'closest_policy':'subject','provenance':{'supervision':{'photo_review_status':'trusted_model'}},
                'warnings':session.get('result',{}).get('warnings',[])}
            return external_document(record,db_document),'haiku_native',record
    if photo.analysis and photo.analysis.get('analysis_source',{}).get('source') in ('aaa','haiku_api','haiku_native'):
        return None,None,None
    distilled=distill_sessions(sessions)
    return (db_document(distilled),'native',None) if complete_native(distilled,DB_ANALYSIS_KEYS) else (None,None,None)


async def run(args):
    # Lazy import keeps the reader and mapping independently testable.
    from analyzer import SessionLocal, Photo, PhotoAnalysisQueue, db_document, DB_ANALYSIS_KEYS, get_image_url, json_path_for
    aaa_dir = args.aaa_dir
    if aaa_dir is None and (args.datadir / 'aaa/golden/labels').is_dir():
        aaa_dir = args.datadir / 'aaa'
    source = AaaSource(aaa_dir, closest_policy=args.aaa_closest) if aaa_dir else None
    if args.aaa_only and source is None:
        raise ValueError('--aaa-only requires an aaa source checkout')
    if source:
        print(f"Disk source index: {len(source.rows)} photos; "
              f"{sum('skip' in item['row'] for item in source.rows.values())} skips; "
              f"{len(source.errors)} invalid answers. Native trusted histories are also checked.", flush=True)
        source.write_index()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = (source.output_dir / 'runs' if source else args.datadir / 'meta' / 'distillation') / f'{stamp}.jsonl'
    report.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    cursor = None
    processed = 0
    source_ids = sorted(source.rows) if args.aaa_only else None
    source_offset = 0
    matched_source_ids = set()
    with report.open('w') as audit, httpx.Client(timeout=60, follow_redirects=True) as client:
        def log(value):
            audit.write(json.dumps(value, sort_keys=True) + '\n')
            audit.flush()
        log({'kind': 'start', 'apply': not args.dry_run, 'aaa_dir': str(aaa_dir) if source else None,
             'closest_policy': args.aaa_closest, 'source_rows': len(source.rows) if source else 0,
             'source_errors': source.errors if source else {}})
        def fetch(url):
            response = client.get(url)
            response.raise_for_status()
            if not response.content or not response.headers.get('content-type', '').startswith('image/'):
                raise ValueError('LLM URL did not return an image')
            return response.content
        while True:
            page_ids = None
            if source_ids is not None:
                page_ids = source_ids[source_offset:source_offset + 200]
                source_offset += 200
                if not page_ids:
                    break
            async with SessionLocal() as db:
                stmt = select(Photo).options(load_only(Photo.id, Photo.analysis, Photo.file_md5, Photo.sizes)).where(Photo.deleted == False, Photo.processing_status == 'completed', Photo.file_md5.isnot(None))
                if page_ids is not None:
                    stmt = stmt.where(Photo.id.in_(page_ids))
                elif cursor is not None:
                    stmt = stmt.where(Photo.id > cursor)
                if getattr(args,'missing_only',False):
                    stmt=stmt.where(or_(Photo.analysis.is_(None),func.jsonb_typeof(Photo.analysis)=='null'))
                if args.photo_ids:
                    stmt = stmt.where(Photo.id.in_(args.photo_ids))
                batch = (await db.execute(stmt.order_by(Photo.id).limit(200))).scalars().all()
            if not batch:
                if source_ids is not None:
                    continue
                break
            for photo in batch:
                cursor = photo.id
                if args.limit is not None and processed >= args.limit:
                    break
                processed += 1
                pid = str(photo.id)
                if source and pid in source.rows:
                    matched_source_ids.add(pid)
                    if 'skip' in source.rows[pid]['row']:
                        counts['source_skipped'] += 1
                        log({'id': pid, 'status': 'source_skipped', 'reason': source.rows[pid]['row']['skip']})
                        continue
                if args.aaa_only and pid not in source.rows:
                    counts['outside_source'] += 1
                    continue
                if not (source and pid in source.rows) and not has_responses(args.datadir, photo):
                    counts['no_complete_answer'] += 1
                    continue
                lock = acquire_file_lock(lock_path_for(json_path_for(args.datadir, photo)), blocking=False)
                if lock is None:
                    counts['locked'] += 1
                    log({'id': pid, 'status': 'locked'})
                    continue
                try:
                    if photo.analysis and photo.analysis.get('analysis_source',{}).get('source') in ('aaa','haiku_api','haiku_native') and not (source and pid in source.rows):
                        # Still allow a direct trusted Haiku history to restore itself.
                        if not has_responses(args.datadir,photo):
                            counts['preserved_external']+=1
                            continue
                    document,origin,record=disk_document(photo,args.datadir,source,persist=not args.dry_run,
                        verify_images=args.verify_images,fetch=fetch)
                    if document is None:
                        counts['no_complete_answer']+=1
                        continue
                    status = 'unchanged' if document == photo.analysis else 'would_update' if args.dry_run else 'updated'
                    if not args.dry_run and status != 'unchanged':
                        async with SessionLocal() as db:
                            # Optimistic check: do not overwrite a concurrently changed
                            # annotation, replaced upload, deleted or unfinished photo.
                            same = or_(Photo.analysis.is_(None), func.jsonb_typeof(Photo.analysis) == 'null') if photo.analysis is None else Photo.analysis == photo.analysis
                            result = await db.execute(update(Photo).where(
                                Photo.id == photo.id, Photo.file_md5 == photo.file_md5, Photo.sizes.cast(JSONB) == photo.sizes, same,
                                Photo.deleted == False, Photo.processing_status == 'completed',
                            ).values(analysis=document))
                            if result.rowcount != 1:
                                status = 'conflict'
                            else:
                                await db.execute(delete(PhotoAnalysisQueue).where(PhotoAnalysisQueue.photo_id == photo.id))
                            await db.commit()
                    counts[status] += 1
                    counts[f'{origin}_complete'] += 1
                    log({'id': pid, 'file_md5': photo.file_md5, 'origin': origin, 'status': status,
                         'before': photo.analysis, 'after': document,
                         'image_hash': record.get('image_hash') if record else None})
                except Exception as error:
                    counts['errors'] += 1
                    log({'id': pid, 'status': 'error', 'error': str(error)})
                finally:
                    release_file_lock(lock)
            print(json.dumps({'visited': processed, **counts}), flush=True)
            if args.limit is not None and processed >= args.limit:
                break
        if source:
            counts['source_rows_visited'] = len(matched_source_ids)
            if not args.photo_ids and args.limit is None and not getattr(args, 'missing_only', False):
                missing = set(source.rows) - matched_source_ids
                counts['source_rows_outside_active_db'] = len(missing)
                from aaa_source import atomic_jsonl
                atomic_jsonl(source.output_dir / 'outside-db.jsonl', ({'photo_id': pid} for pid in sorted(missing)))
        log({'kind': 'summary', 'visited': processed, **counts})
    print(f'Distillation audit: {report}', flush=True)
    return 1 if counts['errors'] or counts['conflict'] or counts['locked'] else 0
