"""Repair proposals must preserve scope and distinguish evidence from inference."""
import copy
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'propose_photo_size_fixes.py'
spec = importlib.util.spec_from_file_location('propose_photo_size_fixes', SCRIPT)
proposal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proposal)


def row(kind='exact-width-height-reversal'):
	return {'id': 'photo-1', 'classification': kind, 'photo_dimensions': [1440, 2560],
	        'full_dimensions': [2560, 1440], 'full_url': 'https://pics.example/full.webp',
	        'ordinary_renditions': [], 'ordinary_aspect_disagrees_full': False,
	        'deleted': False, 'processed_at': '2026-01-01', 'orientation': '6', 'detections': 2}


def test_row_repair_uses_full_header_and_changes_only_the_row_dimensions():
	item = row()
	before = copy.deepcopy(item)
	out = proposal.build_proposal(item, {('photo-1', 'sizes.full'): {'actual_dimensions': [2560, 1440]}})
	assert item == before
	assert out['status'] == 'verified'
	assert [(c['path'], c['before'], c['after']) for c in out['changes']] == [
		('photos.width/height', [1440, 2560], [2560, 1440])]


def test_missing_or_conflicting_evidence_does_not_mark_a_swap_verified():
	item = row()
	assert proposal.build_proposal(item, {})['status'] == 'needs-check'
	assert proposal.build_proposal(item, {('photo-1', 'sizes.full'): {'error': '404'}})['status'] == 'blocked'
	assert proposal.build_proposal(item, {('photo-1', 'sizes.full'): {'actual_dimensions': [1440, 2560]}})['status'] == 'blocked'


def test_rendition_proposals_are_per_field_with_independent_statuses():
	item = row('exact-match')
	item.update(photo_dimensions=[2560, 1440], ordinary_aspect_disagrees_full=True)
	item['ordinary_renditions'] = [
		{'name': '320', 'dimensions': [180, 320], 'url': 'https://pics.example/320.webp'},
		{'name': '640', 'dimensions': [360, 640], 'url': 'https://pics.example/640.webp'},
		{'name': '1024', 'dimensions': [1024, 576], 'url': 'https://pics.example/1024.webp'},
	]
	out = proposal.build_proposal(item, {('photo-1', 'sizes.320'): {'actual_dimensions': [320, 180]}})
	assert out['status'] == 'needs-check'
	assert [(c['path'], c['after'], c['status']) for c in out['changes']] == [
		('sizes.320.width/height', [320, 180], 'verified'),
		('sizes.640.width/height', [640, 360], 'needs-check')]
	assert all(c['path'] != 'photos.width/height' for c in out['changes'])


def test_panorama_needs_original_dzi_size_not_capped_full():
	item = row('other-aspect-mismatch')
	item.update(photo_dimensions=[156962, 8366], full_dimensions=[8192, 554])
	checks = {('photo-1', 'sizes.full'): {'actual_dimensions': [8192, 554]}}
	assert proposal.build_proposal(item, checks)['changes'][0]['after'] is None
	evidence = {'id': 'photo-1', 'actual_dzi_dimensions': {'Width': '157180', 'Height': '10646'},
	            'full': {'pyramid': {'width': 157180, 'height': 10646}}}
	out = proposal.build_proposal(item, checks, evidence)
	assert out['changes'][0]['after'] is None
	assert out['status'] == 'needs-check'
	source = {'id': 'photo-1', 'dimensions': [157180, 10646], 'source': 'original EXR header'}
	out = proposal.build_proposal(item, checks, evidence, source)
	assert out['changes'][0]['after'] == [157180, 10646]
	assert out['status'] == 'verified'
	source['dimensions'] = item['photo_dimensions']
	out = proposal.build_proposal(item, checks, evidence, source)
	assert out['changes'][0]['after'] is None
	assert out['status'] == 'blocked'
	assert '156962 × 8366' in out['changes'][0]['evidence']
	assert proposal.build_proposal(item, checks, evidence, {**source, 'id': 'other'})['status'] == 'needs-check'
	evidence['full']['pyramid']['dzi_url'] = 'https://pics.example/photo-1.dzi'
	out = proposal.build_proposal(item, checks, evidence, source, match_uploaded_artifacts=True)
	assert out['status'] == 'verified'
	assert out['changes'][0]['after'] == [157180, 10646]
	assert out['changes'][0]['artifact'] == {'kind': 'dzi', 'url': 'https://pics.example/photo-1.dzi',
	                                        'dimensions': [157180, 10646]}
	assert out['original_source_evidence'] == source
	assert 'retain uploaded artifacts' in out['changes'][0]['evidence']
	bad = {**evidence, 'id': 'different-photo'}
	assert proposal.build_proposal(item, checks, bad)['status'] == 'needs-check'


def test_cached_generic_ordinary_check_matches_only_the_correct_variant():
	item = row('exact-match')
	item.update(photo_dimensions=[2560, 1440], ordinary_aspect_disagrees_full=True)
	item['ordinary_renditions'] = [
		{'name': '320', 'dimensions': [180, 320], 'url': 'https://pics.example/320.webp'},
		{'name': '640', 'dimensions': [360, 640], 'url': 'https://pics.example/640.webp'}]
	jobs = proposal.image_jobs([item])
	cached = [{'id': 'photo-1', 'kind': 'ordinary', 'expected_dimensions': [360, 640],
	           'actual_dimensions': [640, 360]}]
	checks = proposal.cached_checks(jobs, cached)
	assert set(checks) == {('photo-1', 'sizes.640')}


def test_report_uses_hillview_photo_route_and_escapes_untrusted_text():
	item = row()
	item['id'] = 'id"><script>bad()</script>'
	out = proposal.build_proposal(item, {})
	plan = {'source': '<script>bad-source</script>', 'photos': [out],
	        'summary': {'dimension_pairs': 1, 'statuses': {'needs-check': 1},
	                    'groups': {'Photo-row dimensions': 1}}}
	html = proposal.render_report(plan, 'https://hillview.cz', 'sizes.json')
	assert 'https://hillview.cz/photo/hillview-id%22%3E%3Cscript%3E' in html
	assert '&lt;script&gt;bad-source&lt;/script&gt;' in html
	assert '<script>bad()' not in html
	assert html.count('<script>') == 1
	assert 'Open in Hillview' in html
	assert 'No pixels or detection coordinates change.' in html


def test_normal_downscales_and_unfinished_rows_are_not_repair_proposals():
	assert not proposal.needs_report(row('normal-full-downscale'))
	assert not proposal.needs_report(row('missing-or-invalid-photo-dimensions'))


def test_webp_header_readers_parse_canvas_and_lossless_frame_dimensions():
	from photo_dimension_headers import image_dimensions

	payload = b'\x00\x00\x00\x00' + (310).to_bytes(3, 'little') + (172).to_bytes(3, 'little')
	data = b'RIFF' + (22).to_bytes(4, 'little') + b'WEBPVP8X' + (10).to_bytes(4, 'little') + payload
	assert image_dimensions(data) == (311, 173)
	bits = 310 | (172 << 14)
	payload = b'\x2f' + bits.to_bytes(4, 'little')
	data = b'RIFF' + (17).to_bytes(4, 'little') + b'WEBPVP8L' + (5).to_bytes(4, 'little') + payload
	assert image_dimensions(data) == (311, 173)
