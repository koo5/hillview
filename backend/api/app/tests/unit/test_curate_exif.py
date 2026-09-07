"""Unit tests for the curated camera EXIF served by GET /api/photos/public/{uid}.

``exif_data['data']`` mixes two exiftool output modes: the worker's own dump is
``-n`` (bare numbers), while pipeline uploads (EXR panos, fused stacks) merge in
the pics pipeline's PrintConv-form snapshot of the source frames
(``"170.0 mm"``, ``"1/500"``, ``"+1/3"``) plus per-frame ``pano_frames`` (one
stack per pano position) / ``stack_frames`` (one stack). The curator must read
both forms and summarise the stacks.
"""
import os
import sys

import pytest

# api/app on the path so route modules import the same way the app does;
# backend root for ``common``.
api_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(api_app_dir))
sys.path.insert(1, os.path.abspath(os.path.join(api_app_dir, '..', '..')))

from photo_routes import _curate_exif, _exif_number  # noqa: E402


@pytest.mark.parametrize('raw, expected', [
	# -n mode passes through untouched.
	(170, 170),
	(9.5, 9.5),
	(0.002, 0.002),
	(-0.333, -0.333),
	# PrintConv strings, as exiftool -j prints them without -n.
	('170.0 mm', 170),
	('18.5 mm', 18.5),
	('255 mm', 255),
	('1/500', 0.002),
	('+1', 1),
	('+1/3', pytest.approx(1 / 3)),
	('-2/3', pytest.approx(-2 / 3)),
	('400', 400),
	# Junk.
	('undef', None),
	('', None),
	('1/0', None),
	('Canon EOS 5D Mark IV', None),
	(True, None),
	(None, None),
	([1, 2], None),
])
def test_exif_number(raw, expected):
	assert _exif_number(raw) == expected


def test_none_without_data():
	assert _curate_exif(None) is None
	assert _curate_exif({}) is None
	assert _curate_exif({'data': 'nope'}) is None
	assert _curate_exif({'data': {'GPSLatitude': 50.1}}) is None


def test_worker_numeric_dump():
	"""A plain JPEG upload: the worker's exiftool -n tags."""
	curated = _curate_exif({'data': {
		'Make': 'Canon', 'Model': 'Canon EOS R6', 'LensModel': 'RF24-70mm F2.8 L IS USM',
		'FocalLength': 24, 'FocalLengthIn35mmFormat': 36,
		'FNumber': 2.8, 'ISO': 200, 'ExposureTime': 0.004, 'ExposureCompensation': 0,
	}})
	assert curated == {
		'make': 'Canon', 'model': 'Canon EOS R6', 'lens': 'RF24-70mm F2.8 L IS USM',
		'focal_length': 24, 'focal_length_35mm': 36,
		'f_number': 2.8, 'iso': 200, 'exposure_time': 0.004, 'exposure_compensation': 0,
	}


def test_printconv_strings_at_top_level():
	"""The user-reported shape: tags in PrintConv form at the top level."""
	curated = _curate_exif({'data': {
		'FocalLength': '170.0 mm', 'ISO': 400, 'ExposureTime': '1/500', 'FNumber': 9.5,
		'ExposureCompensation': '-1/3',
	}})
	assert curated == {
		'focal_length': 170, 'iso': 400, 'exposure_time': 0.002, 'f_number': 9.5,
		'exposure_compensation': pytest.approx(-1 / 3),
	}


def _frame(et, iso=400, fn=9.5):
	return {'Make': 'Canon', 'Model': 'Canon EOS 5D Mark IV', 'LensModel': 'EF70-200mm f/4L IS USM',
			'FocalLength': '170.0 mm', 'ISO': iso, 'ExposureTime': et, 'FNumber': fn,
			'DateTimeOriginal': '2026:08:30 10:00:00'}


def _bracket(iso=400):
	return [_frame('1/500', iso), _frame('1/2000', iso), _frame('1/125', iso)]


PANO_HEADER = {
	'Make': 'Canon', 'Model': 'Canon EOS 5D Mark IV', 'LensModel': 'EF70-200mm f/4L IS USM',
	'FocalLength': '170.0 mm',
}


def test_exr_pano_uniform_brackets():
	"""An EXR pano: identity header only (no embedded exposure) and the same
	bracket at every position. Shutter varies within the bracket → range;
	ISO/aperture constant → scalars; nothing mixed; frames counted across
	positions."""
	curated = _curate_exif({'data': {**PANO_HEADER, 'pano_frames': [_bracket(), _bracket(), _bracket()]}})
	assert curated == {
		'make': 'Canon', 'model': 'Canon EOS 5D Mark IV', 'lens': 'EF70-200mm f/4L IS USM',
		'focal_length': 170,
		'f_number': 9.5, 'iso': 400, 'exposure_time_range': [0.0005, 0.008],
		'frames': 9, 'positions': 3,
	}


def test_exr_pano_one_position_disagrees():
	"""Positions don't all share the bracket: the predominant summary is sent
	and flagged mixed. ISO is constant within each stack but 800 at one
	position → scalar 400 + mixed; the odd position's narrower bracket → the
	common range + mixed."""
	odd = [_frame('1/250', iso=800), _frame('1/1000', iso=800)]
	curated = _curate_exif({'data': {**PANO_HEADER, 'pano_frames': [_bracket(), odd, _bracket()]}})
	assert curated['iso'] == 400
	assert curated['iso_mixed'] is True
	assert curated['exposure_time_range'] == [0.0005, 0.008]
	assert curated['exposure_time_mixed'] is True
	assert curated['f_number'] == 9.5
	assert 'f_number_mixed' not in curated
	assert curated['frames'] == 8
	assert curated['positions'] == 3


def test_tie_keeps_pto_order():
	"""Two positions, two different brackets: the first in pto order wins."""
	curated = _curate_exif({'data': {'pano_frames': [
		[_frame('1/500'), _frame('1/125')],
		[_frame('1/250'), _frame('1/1000')],
	]}})
	assert curated['exposure_time_range'] == [0.002, 0.008]
	assert curated['exposure_time_mixed'] is True


def test_fused_stack_prefers_frames_over_embedded_anchor():
	"""A fused-stack TIFF embeds only its anchor frame's exposure (worker -n
	numbers); the flat stack_frames carry the whole bracket, which wins. One
	stack → no positions, nothing mixed."""
	curated = _curate_exif({'data': {
		'Make': 'Canon', 'Model': 'Canon EOS 5D Mark IV',
		'FocalLength': 170, 'FNumber': 9.5, 'ISO': 400, 'ExposureTime': 0.002,
		'stack_frames': [_frame('1/500'), _frame('1/2000', iso=800), _frame('1/125', iso=100)],
	}})
	assert curated['exposure_time_range'] == [0.0005, 0.008]
	assert curated['iso_range'] == [100, 800]
	assert curated['f_number'] == 9.5
	assert curated['frames'] == 3
	assert 'positions' not in curated
	assert not any(k.endswith('_mixed') for k in curated)


def test_single_frame_stack_is_a_scalar():
	curated = _curate_exif({'data': {'stack_frames': [_frame('1/500')]}})
	assert curated['exposure_time'] == 0.002
	assert curated['frames'] == 1
	assert 'positions' not in curated


def test_frames_lacking_a_tag_fall_back_to_top_level():
	"""Frames without FNumber at all → the photo's own tag is used for it."""
	frames = [{k: v for k, v in _frame('1/60').items() if k != 'FNumber'}]
	curated = _curate_exif({'data': {'FNumber': 8, 'stack_frames': frames}})
	assert curated['f_number'] == 8
	assert curated['exposure_time'] == pytest.approx(1 / 60)


def test_malformed_frames_are_skipped():
	curated = _curate_exif({'data': {
		'ISO': 100,
		'pano_frames': ['garbage', [], [None, 3, _frame('1/60', iso=200)]],
		'stack_frames': 'nope',
	}})
	# The one real frame supplies the triangle; ISO from it, not the top level.
	assert curated['iso'] == 200
	assert curated['exposure_time'] == pytest.approx(1 / 60)
	assert curated['frames'] == 1
	assert 'positions' not in curated


def test_frames_alone_do_not_fabricate_exif():
	"""Frames that carry no readable tags must not yield a bare {'frames': n}."""
	assert _curate_exif({'data': {'pano_frames': [[{'DateTimeOriginal': 'x'}]]}}) is None


def test_phone_zero_35mm_is_dropped():
	"""Ulefone Armor 22 (18k prod rows): CameraX writes FocalLengthIn35mmFormat
	as 0, which used to render as "5.58 mm (0 mm eq.)"."""
	curated = _curate_exif({'data': {
		'Make': 'Ulefone', 'Model': 'Armor 22', 'FocalLength': 5.58, 'FocalLengthIn35mmFormat': 0,
		'FNumber': 1.89, 'ISO': 100, 'ExposureTime': 0.001536, 'ExposureCompensation': 0,
	}})
	assert curated['focal_length'] == 5.58
	assert 'focal_length_35mm' not in curated
	assert curated['iso'] == 100 and curated['f_number'] == 1.89 and curated['exposure_time'] == 0.001536


def test_dslr_without_35mm_tag():
	"""Canon EOS 5DS (5k prod rows): full frame, no FocalLengthIn35mmFormat; the
	exiftool composite FocalLength35efl is sensor-math noise and is ignored."""
	curated = _curate_exif({'data': {
		'Make': 'Canon', 'Model': 'Canon EOS 5DS', 'LensModel': 'EF70-200mm f/4L IS USM',
		'LensID': 'Canon EF 70-200mm f/4L IS USM', 'FocalLength': 70, 'FocalLength35efl': 68.4587777880589,
		'FNumber': 8, 'ISO': 100, 'ExposureTime': 0.002, 'ExposureCompensation': 0,
	}})
	assert curated['focal_length'] == 70
	assert 'focal_length_35mm' not in curated
	assert curated['lens'] == 'EF70-200mm f/4L IS USM'
