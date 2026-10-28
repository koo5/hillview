"""Dimension categories must not confuse ordinary downscaling with reversals."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'audit_photo_dimensions.py'
spec = importlib.util.spec_from_file_location('audit_photo_dimensions', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.mark.parametrize(('photo', 'full', 'kind'), [
	((2560, 1440), (2560, 1440), 'exact-match'),
	((1440, 2560), (2560, 1440), 'exact-width-height-reversal'),
	((40000, 20000), (8192, 4096), 'normal-full-downscale'),
	((20000, 40000), (8192, 4096), 'reversed-aspect-full-downscale'),
	((6000, 4000), (1024, 683), 'normal-full-downscale'),
	((4000, 6000), (1024, 683), 'reversed-aspect-full-downscale'),
	((100, 80), (200, 160), 'same-aspect-full-larger'),
	((80, 100), (200, 160), 'reversed-aspect-full-larger'),
	((3000, 2000), (1000, 1000), 'other-aspect-mismatch'),
	(None, (100, 80), 'missing-or-invalid-photo-dimensions'),
	((100, 80), None, 'missing-or-invalid-full-dimensions'),
])
def test_classification(photo, full, kind):
	assert audit.classify(photo, full) == kind


def test_photo_bounds_failure_can_be_metadata_reversal_without_invalid_boxes():
	checker = audit.Audit()
	row = {'id': 'orientation-example', 'width': 1440, 'height': 2560,
	       'sizes': {'full': {'width': 2560, 'height': 1440},
	                 '1024': {'width': 1024, 'height': 576, 'url': 'https://example/image.webp'}},
	       'detected_objects': {'objects': [{'bbox': {'x1': 1801, 'y1': 606, 'x2': 2193, 'y2': 684}}]},
	       'processed_at': None, 'processing_status': 'completed', 'deleted': False,
	       'orientation': '6', 'processed_by_worker': 'worker'}
	result = checker.add(row)
	assert result['classification'] == 'exact-width-height-reversal'
	assert result['boxes_exceeding_photo'] == 1
	assert result['boxes_exceeding_full'] == 0
	assert result['ordinary_aspects_agree_full'] == 1
	assert result['ordinary_aspects_agree_photo'] == 0
	assert checker.report()['bbox_checks']['photo_bound_errors_resolved_by_reversal'] == 1
	assert not result['legacy_fix_sizes_selection']  # full metadata is already landscape


def test_old_fix_selection_can_match_even_when_photo_and_full_metadata_agree():
	checker = audit.Audit()
	result = checker.add({'id': 'old-fix-target', 'width': 1440, 'height': 2560,
	    'sizes': {'full': {'width': 1440, 'height': 2560}, '320': {'width': 320, 'height': 180}},
	    'detected_objects': None, 'processed_at': None, 'processing_status': 'completed',
	    'deleted': False, 'orientation': None, 'processed_by_worker': None})
	assert result['classification'] == 'exact-match'
	assert result['ordinary_aspect_disagrees_full'] is True
	assert result['legacy_fix_sizes_selection'] is True
