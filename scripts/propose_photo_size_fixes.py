#!/usr/bin/env python3
"""Generate a static HTML report and JSON plan of proposed dimension repairs.

Reads saved audit JSONL and optional header/DZI evidence. No DB connection or
write/apply mode. --check-images verifies missing evidence with bounded HTTP
header reads; existing matching checks are reused. Only width/height fields are
proposed. All candidates, including unverified and blocked ones, remain visible.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_photo_dimensions import dimensions, same_aspect
from photo_dimension_headers import check_image


def read_jsonl(path):
	return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path else []


def http_url(value):
	return value if isinstance(value, str) and urlsplit(value).scheme in ('http', 'https') and urlsplit(value).netloc else None


def needs_report(row):
	return row['classification'] in ('exact-width-height-reversal', 'other-aspect-mismatch') or row.get('ordinary_aspect_disagrees_full', False)


def image_jobs(rows):
	jobs = {}
	for row in rows:
		jobs[(row['id'], 'sizes.full')] = {'id': row['id'], 'field': 'sizes.full',
			'url': row.get('full_url'), 'expected_dimensions': row['full_dimensions']}
		if row.get('ordinary_aspect_disagrees_full'):
			for variant in row['ordinary_renditions']:
				if same_aspect(variant['dimensions'], row['full_dimensions']):
					continue
				field = f'sizes.{variant["name"]}'
				jobs[(row['id'], field)] = {'id': row['id'], 'field': field,
					'url': variant.get('url'), 'expected_dimensions': variant['dimensions']}
	return jobs


def cached_checks(jobs, cached):
	checks = {}
	for key, job in jobs.items():
		for record in cached:
			if record['id'] != job['id'] or record.get('expected_dimensions') != job['expected_dimensions']:
				continue
			if record.get('field') not in (None, job['field']):
				continue
			if record.get('kind') == 'full' and job['field'] != 'sizes.full':
				continue
			if record.get('kind') == 'ordinary' and job['field'] == 'sizes.full':
				continue
			checks[key] = {**record, 'field': job['field'], 'evidence_source': 'saved header check'}
			break
	return checks


def field_proposal(path, before, after, check=None, evidence=''):
	status = 'needs-check'
	if check and check.get('error'):
		status, evidence = 'blocked', check['error']
	elif check and check.get('actual_dimensions'):
		actual = check['actual_dimensions']
		if actual == after:
			status = 'verified'
			evidence = f'Image header: {actual[0]} × {actual[1]}'
		else:
			status = 'blocked'
			evidence = f'Header {actual[0]} × {actual[1]} contradicts this proposal'
	return {'path': path, 'before': before, 'after': after, 'status': status,
	        'evidence': evidence or 'Image-header check needed'}


def build_proposal(row, checks, dzi_evidence=None, source_evidence=None, *, match_uploaded_artifacts=False):
	photo, full = row['photo_dimensions'], row['full_dimensions']
	full_check = checks.get((row['id'], 'sizes.full'))
	changes = []
	issues = []
	if row['classification'] == 'exact-width-height-reversal':
		group = 'Photo-row dimensions'
		changes.append(field_proposal('photos.width/height', photo, full, full_check))
	elif row['classification'] == 'other-aspect-mismatch':
		group = 'Panorama dimensions'
		verified_dzi = None
		if dzi_evidence and dzi_evidence.get('id') == row['id']:
			actual = dzi_evidence.get('actual_dzi_dimensions') or {}
			try:
				verified_dzi = dimensions(int(actual['Width']), int(actual['Height']))
			except (KeyError, ValueError, TypeError):
				pass
			pyramid = (dzi_evidence.get('full') or {}).get('pyramid') or {}
			if verified_dzi != dimensions(pyramid.get('width'), pyramid.get('height')):
				verified_dzi = None
		source_size = None
		if source_evidence and source_evidence.get('id') == row['id']:
			source_dims = source_evidence.get('dimensions')
			if isinstance(source_dims, (list, tuple)) and len(source_dims) == 2:
				source_size = dimensions(*source_dims)
		if match_uploaded_artifacts and verified_dzi and same_aspect(verified_dzi, full) and full_check and full_check.get('actual_dimensions') == full:
			evidence = 'Match the actual uploaded DZI; its descriptor agrees with saved pyramid metadata and the full-image aspect.'
			if source_size and source_size != verified_dzi:
				evidence += f' Archived source is {source_size[0]} × {source_size[1]}; retain uploaded artifacts per operator decision, without reuploading.'
			changes.append({'path': 'photos.width/height', 'before': photo, 'after': list(verified_dzi),
			                'status': 'verified', 'evidence': evidence})
		elif source_size and verified_dzi and source_size != verified_dzi:
			changes.append({'path': 'photos.width/height', 'before': photo, 'after': None,
			                'status': 'blocked', 'evidence': f'Original source header: {source_size[0]} × {source_size[1]}; rendered DZI: {verified_dzi[0]} × {verified_dzi[1]}. Resolve source/output disagreement before changing dimensions.'})
		elif source_size and verified_dzi and same_aspect(verified_dzi, full) and full_check and full_check.get('actual_dimensions') == full:
			changes.append({'path': 'photos.width/height', 'before': photo, 'after': list(verified_dzi),
			                'status': 'verified', 'evidence': 'Original source header agrees with actual DZI descriptor, pyramid metadata and full-image aspect'})
		else:
			changes.append({'path': 'photos.width/height', 'before': photo, 'after': None,
			                'status': 'needs-check', 'evidence': 'Check original source header as well as rendered DZI; output dimensions alone cannot establish which source was rendered'})
	else:
		group = 'Rendition metadata'
	if row.get('ordinary_aspect_disagrees_full'):
		for variant in row['ordinary_renditions']:
			old = variant['dimensions']
			if same_aspect(old, full):
				continue
			path = f'sizes.{variant["name"]}.width/height'
			if same_aspect(old[::-1], full):
				changes.append(field_proposal(path, old, old[::-1], checks.get((row['id'], f'sizes.{variant["name"]}'))))
			else:
				issues.append(f'{path}: not a simple reversal; inspect source geometry')
	for change in changes:
		if change['path'] == 'photos.width/height':
			if row['classification'] == 'other-aspect-mismatch':
				pyramid = ((dzi_evidence or {}).get('full') or {}).get('pyramid') or {}
				artifact = {'kind': 'dzi', 'url': pyramid.get('dzi_url'), 'dimensions': change['after']}
			else:
				artifact = {'kind': 'image', 'url': row.get('full_url'), 'dimensions': change['after']}
		else:
			name = change['path'].split('.')[1]
			variant = next(v for v in row['ordinary_renditions'] if v['name'] == name)
			artifact = {'kind': 'image', 'url': variant.get('url'), 'dimensions': change['after']}
		change['artifact'] = artifact
	statuses = [c['status'] for c in changes]
	status = 'blocked' if 'blocked' in statuses or issues else 'needs-check' if 'needs-check' in statuses else 'verified'
	variants = [v for v in row['ordinary_renditions'] if http_url(v.get('url'))]
	preview = min(variants, key=lambda v: abs(int(v['name']) - 640)) if variants else None
	return {'id': row['id'], 'group': group, 'status': status, 'deleted': row['deleted'],
	        'processed_at': row['processed_at'], 'orientation': row['orientation'],
	        'photo_dimensions': photo, 'full_dimensions': full, 'changes': changes, 'issues': issues,
	        'preview_url': preview['url'] if preview else http_url(row.get('full_url')),
	        'full_url': http_url(row.get('full_url')), 'detections': row['detections'],
	        'original_source_evidence': source_evidence}


def dims(pair):
	return f'{pair[0]:,} × {pair[1]:,}' if pair else 'Undetermined'


def render_report(plan, hillview_url, plan_name):
	parts = []
	for row in plan['photos']:
		link = f'{hillview_url.rstrip("/")}/photo/{quote("hillview-" + row["id"], safe="")}'
		image = f'<img src="{escape(row["preview_url"], quote=True)}" loading="lazy" alt="Photo preview">' if row['preview_url'] else ''
		change_rows = ''.join(f'<tr><td>{escape(change["path"])}</td><td>{dims(change["before"])}</td>'
			f'<td>→ {dims(change["after"])}</td><td class="{change["status"]}">{change["status"]}</td>'
			f'<td>{escape(change["evidence"])}</td></tr>' for change in row['changes'])
		issues = ''.join(f'<p>{escape(issue)}</p>' for issue in row['issues'])
		full_link = f'<a href="{escape(row["full_url"], quote=True)}" target="_blank" rel="noreferrer">Full image</a>' if row['full_url'] else ''
		parts.append(f'''<tr class="photo" data-group="{escape(row['group'], quote=True)}" data-status="{row['status']}" data-id="{escape(row['id'], quote=True)}">
<td><a href="{escape(link, quote=True)}" target="_blank" rel="noreferrer">{image}<br>{escape(row['id'])}</a><br>
<a href="{escape(link, quote=True)}" target="_blank" rel="noreferrer">Open in Hillview ↗</a> · {full_link}
<div class="muted">{escape(str(row['processed_at']))}<br>{'Deleted · ' if row['deleted'] else ''}{row['detections']} detections · orientation {escape(str(row['orientation']))}</div></td>
<td><strong>{escape(row['group'])}</strong><br>Photo row: {dims(row['photo_dimensions'])}<br>Full: {dims(row['full_dimensions'])}
<table class="changes"><thead><tr><th>Field</th><th>Stored</th><th>Proposed</th><th>Evidence status</th><th>Evidence</th></tr></thead><tbody>{change_rows}</tbody></table>{issues}</td></tr>''')
	groups = ''.join(f'<option>{escape(group)}</option>' for group in plan['summary']['groups'])
	return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Proposed photo size fixes</title><style>
:root{color-scheme:dark;font:12px system-ui;background:#101820;color:#e9eef2}body{margin:6px}h1{font-size:17px;margin:3px 0}p{margin:4px 0}a{color:#a9d0ff}
button,input,select{font:12px system-ui;padding:2px 4px;background:#253847;color:inherit;border:1px solid #587083;border-radius:0}
.controls{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}table{border-collapse:collapse;width:100%}td,th{padding:4px 6px;text-align:left;vertical-align:top;border-bottom:1px solid #385061}
th{background:#1c2a36}thead{position:sticky;top:0}table.changes{margin-top:5px;font-size:11px}table.changes thead{position:static}table.changes td{white-space:nowrap}
table.changes td:last-child{white-space:normal}td:first-child img{width:110px;height:64px;object-fit:contain}table.main>tbody>tr>td:first-child{width:260px;font:11px ui-monospace,monospace}
.verified{color:#72e6a2}.needs-check{color:#ffd38e}.blocked{color:#ff9696}.muted{color:#a9bdc9;font-size:11px;margin-top:4px}[hidden]{display:none!important}
</style><h1>Proposed photo size fixes</h1>''' + f'''
<p><strong>Review only · no changes applied.</strong> {len(plan['photos'])} photos · {plan['summary']['dimension_pairs']} dimension pairs ·
<span class="verified">{plan['summary']['statuses'].get('verified', 0)} verified photos</span> ·
<span class="needs-check">{plan['summary']['statuses'].get('needs-check', 0)} needing checks</span> ·
<span class="blocked">{plan['summary']['statuses'].get('blocked', 0)} blocked</span>.</p>
<p>{escape(plan['source'])}. Proposals use the saved audit and image-header/DZI evidence; stored values become preconditions for any later repair.</p>
<p>Dimension basis: <strong>{escape(plan.get('dimension_basis', 'original-source'))}</strong>. Each proposed field has its own evidence. With uploaded-artifacts as the basis, panorama dimensions follow the served DZI even when the archived source differs. No pixels or detection coordinates change.
<a download href="{escape(plan_name, quote=True)}">Download JSON plan</a></p>
<div class="controls"><select id="group"><option value="">All kinds</option>{groups}</select>
<select id="status"><option value="">All evidence statuses</option><option>verified</option><option>needs-check</option><option>blocked</option></select>
<input id="search" placeholder="Find photo ID" aria-label="Find photo ID"><span id="count"></span></div>
<table class="main"><thead><tr><th>Photo · Hillview link</th><th>Proposed metadata fixes</th></tr></thead><tbody>{''.join(parts)}</tbody></table>''' + '''
<script>(()=>{const rows=[...document.querySelectorAll('tr.photo')],group=document.querySelector('#group'),status=document.querySelector('#status'),search=document.querySelector('#search');
function filter(){let n=0;for(const row of rows){row.hidden=!!((group.value&&row.dataset.group!==group.value)||(status.value&&row.dataset.status!==status.value)||!row.dataset.id.includes(search.value.trim()));if(!row.hidden)n++;}document.querySelector('#count').textContent=`${n} / ${rows.length} photos`;}
group.addEventListener('change',filter);status.addEventListener('change',filter);search.addEventListener('input',filter);filter();})();</script></html>'''


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--anomalies', type=Path, required=True)
	parser.add_argument('--header-checks', type=Path)
	parser.add_argument('--dzi-evidence', type=Path)
	parser.add_argument('--source-evidence', type=Path, help='Original-source header JSONL: id, dimensions [width, height], source description')
	parser.add_argument('--match-uploaded-artifacts', action='store_true', help='Use served DZI dimensions even when the original source differs; preserve source evidence in the plan')
	parser.add_argument('--audit-report', type=Path)
	parser.add_argument('--check-images', action='store_true', help='Fetch missing header evidence (read-only, max 64 KiB per image)')
	parser.add_argument('--workers', type=int, default=6)
	parser.add_argument('--hillview-url', default='https://hillview.cz')
	parser.add_argument('--output', type=Path, required=True)
	args = parser.parse_args()
	if not http_url(args.hillview_url) or not 1 <= args.workers <= 12:
		parser.error('Need an HTTP(S) Hillview URL and --workers in [1, 12]')
	rows = [row for row in read_jsonl(args.anomalies) if needs_report(row)]
	jobs = image_jobs(rows)
	checks = cached_checks(jobs, read_jsonl(args.header_checks))
	missing = [job for key, job in jobs.items() if key not in checks]
	print(f'{len(rows)} photos; {len(checks)} cached header checks; {len(missing)} missing', file=sys.stderr)
	if args.check_images and missing:
		with ThreadPoolExecutor(max_workers=args.workers) as pool:
			futures = [pool.submit(check_image, job) for job in missing]
			for index, future in enumerate(as_completed(futures), 1):
				check = future.result()
				checks[(check['id'], check['field'])] = check
				if index % 50 == 0:
					print(f'Checked {index}/{len(missing)} new image headers', file=sys.stderr, flush=True)
	dzi = json.loads(args.dzi_evidence.read_text()) if args.dzi_evidence else None
	sources = {item['id']: item for item in read_jsonl(args.source_evidence)}
	photos = [build_proposal(row, checks, dzi, sources.get(row['id']),
	                         match_uploaded_artifacts=args.match_uploaded_artifacts) for row in rows]
	photos.sort(key=lambda row: (row['group'], str(row['processed_at']), row['id']))
	audit = json.loads(args.audit_report.read_text()) if args.audit_report else {}
	plan = {'version': 2, 'generated_at': datetime.now(timezone.utc).isoformat(),
	        'dimension_basis': 'uploaded-artifacts' if args.match_uploaded_artifacts else 'original-source',
	        'source': audit.get('source', 'Saved photo-dimension audit'), 'audit_snapshot': audit.get('snapshot'),
	        'summary': {'photos': len(photos), 'dimension_pairs': sum(len(row['changes']) for row in photos),
	                    'statuses': dict(Counter(row['status'] for row in photos)),
	                    'field_statuses': dict(Counter(change['status'] for row in photos for change in row['changes'])),
	                    'groups': dict(Counter(row['group'] for row in photos))},
	        'photos': photos}
	args.output.parent.mkdir(parents=True, exist_ok=True)
	plan_path = args.output.with_suffix('.json')
	plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n')
	args.output.with_suffix('.headers.jsonl').write_text('\n'.join(json.dumps(check) for check in checks.values()) + '\n')
	args.output.write_text(render_report(plan, args.hillview_url, quote(plan_path.name)))
	print(json.dumps({'output': str(args.output.resolve()), 'plan': str(plan_path.resolve()), **plan['summary']}, indent=2))


if __name__ == '__main__':
	main()
