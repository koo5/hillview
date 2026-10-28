"""Deterministic review sampling, safe rendering and ordinary rendition choice."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys

SCRIPT = Path(__file__).resolve().parents[1] / 'detections_review.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('detections_review', SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def row(identifier, date, confidence=None, box=None, changes=True):
	obj = {'bbox': box or {'x1': 1, 'y1': 2, 'x2': 30, 'y2': 40}, 'class_id': 0}
	if confidence is not None:
		obj['confidence'] = confidence
	return {'id': identifier, 'processed_at': date, 'captured_at': None,
	        'width': 100, 'height': 80, 'changes': changes,
	        'before': {'objects': [obj]},
	        'after': {'objects': [{**obj, 'blurred': confidence is None or confidence >= .4}]},
	        'sizes': {'1024': {'url': 'https://pics.example/photo.webp'}},
	        }


def test_sampling_covers_each_side_and_is_independent_of_query_order():
	boundary = review.TRANSITIONS[0][1]
	rows = [row(str(i), boundary + timedelta(hours=i)) for i in range(-10, 11)]
	rows.append(row('outside-window', boundary - timedelta(days=10)))
	selected = review.select_samples(rows, per_side=4, extras=0)
	assert selected == review.select_samples(list(reversed(rows)), per_side=4, extras=0)
	assert len(selected) == 8
	assert {'-1', '-2', '0', '1'} <= {r['id'] for r in selected}
	assert 'outside-window' not in {r['id'] for r in selected}
	assert sum('before' in r['groups'][0] for r in selected) == 4
	assert sum('after' in r['groups'][0] for r in selected) == 4


def test_overlapping_transition_samples_are_deduplicated_and_controls_labeled():
	date = datetime(2026, 6, 12, 12, tzinfo=timezone.utc)
	selected = review.select_samples([row('overlap', date), row('control', review.TRANSITIONS[-1][1], changes=False)],
	                                 per_side=1, extras=0)
	assert len(selected) == 2
	assert len(next(r for r in selected if r['id'] == 'overlap')['groups']) == 2
	assert next(r for r in selected if r['id'] == 'control')['changes'] is False


def test_extra_strata_capture_visible_detections_and_dimension_exceptions():
	date = datetime(2025, 11, 1, tzinfo=timezone.utc)
	rows = [row('visible', date, confidence=.3999), row('ordinary', date),
	        row('bounds', None, box={'x1': 0, 'y1': 0, 'x2': 101, 'y2': 80})]
	selected = review.select_samples(rows, extras=2)
	assert {r['id'] for r in selected} == {'visible', 'bounds'}
	assert selected[0]['groups'] == ['Visible legacy detections (< 0.4)']
	assert selected[1]['groups'] == ['Boxes exceeding stored dimensions']


def test_variant_ignores_crops_llm_and_unsafe_urls():
	sizes = {'640_llm': {'url': 'https://pics.example/blackout.webp'},
	         '1024_crop': {'url': 'https://pics.example/crop.webp'},
	         'full': {'url': 'https://pics.example/full.webp'},
	         '1024': {'url': 'javascript:alert(1)'},
	         '640': {'url': 'https://pics.example/640.webp'}}
	assert review.image_variant(sizes)['name'] == '640'
	sizes['1024']['url'] = 'https://pics.example/1024.webp'
	assert review.image_variant(sizes)['name'] == '1024'
	assert review.image_variant({'full': sizes['full']})['name'] == 'full'
	assert review.image_variant({'640_llm': sizes['640_llm']}) is None


def test_html_escapes_json_metadata_and_attributes_and_identifies_controls():
	item = row('id" onload="bad', review.TRANSITIONS[-1][1], changes=False)
	item['groups'] = ['group <b>unsafe</b>']
	item['before']['objects'][0]['class_name'] = '</pre><script>bad()</script>'
	item['after']['objects'][0]['class_name'] = '</pre><script>bad()</script>'
	output = review.render_html([item], '<script>bad-source</script>')
	assert output.count('<script>') == 1  # only the report's own fixed JavaScript
	assert '</pre><script>bad()' not in output
	assert '&lt;script&gt;bad-source&lt;/script&gt;' in output
	assert '&lt;/pre&gt;&lt;script&gt;bad()' in output
	assert 'data-id="id&quot; onload=&quot;bad"' in output
	assert 'already explicit control' in output
	assert 'no migration applied' in output
	assert '__PHOTO_CARDS__' not in output
	assert 'viewBox="0 0 100 80"' in output
	assert '<details class="object-list" open>' in output
	assert 'Stored bbox (px)' in output
	assert 'Rendition bbox (px)' in output
	assert 'class="overlay-toggle" checked' in output


def test_full_and_photo_dimensions_are_separate_and_original_boxes_are_kept():
	item = row('orientation-example', review.TRANSITIONS[0][1],
	           box={'x1': 1801, 'y1': 606, 'x2': 2193, 'y2': 684})
	item.update(width=1440, height=2560, groups=['Boxes exceeding stored dimensions'])
	item['sizes']['full'] = {'url': 'https://pics.example/full.webp', 'width': 2560, 'height': 1440}
	output = review.card_html(item)
	assert 'Photo row: 1440 × 2560' in output
	assert 'Full image: 2560 × 1440' in output
	assert 'value="1440,2560"' in output
	assert 'value="2560,1440" selected' in output
	assert 'Viewer defaults to full-image coordinates. Stored boxes are unchanged.' in output
	assert 'viewBox="0 0 2560 1440"' in output
	assert '(1801, 606) → (2193, 684)' in output
	assert 'data-bbox="[1801, 606, 2193, 684]"' in output
