"""photos.pitch and photos.roll from the capture stamp: common/capture_pose.py.

The real rows are from the deliberate roll series of 2026-11-15 (shared link
35), whose images were checked by eye: rotating each back by the roll below
levels it. See docs/todo/photo-pose-and-level-gates.md.
"""
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from common.capture_pose import capture_pose, level_roll


def exif(stamp) -> dict:
	"""exif_data as stored, with the stamp serialized into UserComment."""
	return {'data': {'UserComment': json.dumps(stamp)}}


def gravity(g) -> dict:
	return exif({'inertial': {'gravity': g}})


def attitude(pitch_deg, roll_deg, rotation=0, version=None, **extra) -> dict:
	stamp = {'attitude': {'pitch_deg': pitch_deg, 'roll_deg': roll_deg, 'device_rotation_deg': rotation}, **extra}
	if version is not None:
		stamp['capture_timing'] = {'metadata_version': version}
	return exif(stamp)


# (gravity, the stamp's pitch_deg / roll_deg / device_rotation_deg, expected GPano pitch, roll).
# In the image: negative roll = horizon falls to the right (scene turned clockwise).
REAL_ROWS = [
	pytest.param([3.802262, 9.020489, -0.640069], -3.741011, 22.856102, 0, 3.741, -22.856, id='portrait-cw'),
	pytest.param([-3.736076, 9.069076, -0.172359], -1.006723, -22.389593, 0, 1.007, 22.390, id='portrait-ccw'),
	pytest.param([2.932063, 9.331985, 0.743736], 4.347999, 17.442457, 0, -4.348, -17.442, id='portrait-looking-down'),
	pytest.param([9.175564, -3.344684, 0.926404], 5.418782, 110.027855, 270, -5.419, -20.028, id='landscape-270-cw'),
	pytest.param([9.472578, 2.447256, 0.71924], 4.204528, 75.514282, 270, -4.205, 14.486, id='landscape-270-ccw'),
	pytest.param([-8.828668, 4.23193, 0.61765], 3.609802, -64.389755, 90, -3.610, -25.610, id='landscape-90-cw'),
	pytest.param([-8.621812, -4.593916, 0.892411], 5.219385, -118.049805, 90, -5.219, 28.050, id='landscape-90-ccw'),
]


@pytest.mark.parametrize('g,pitch_deg,roll_deg,rotation,pitch,roll', REAL_ROWS)
def test_real_rows_from_gravity(g, pitch_deg, roll_deg, rotation, pitch, roll):
	assert capture_pose(gravity(g)) == pytest.approx((pitch, roll), abs=0.01)


@pytest.mark.parametrize('g,pitch_deg,roll_deg,rotation,pitch,roll', REAL_ROWS)
def test_real_rows_from_their_attitude_stamp(g, pitch_deg, roll_deg, rotation, pitch, roll):
	"""The version-3 stamp of the same frame gives the same answer without gravity."""
	assert capture_pose(attitude(pitch_deg, roll_deg, rotation, version=3)) == pytest.approx((pitch, roll), abs=0.01)


def test_a_lens_above_the_horizon_has_positive_pitch():
	# Gravity pointing out of the screen's back (negative z) means the camera looks up.
	pitch, roll = capture_pose(gravity([0.0, 9.0, -3.9]))
	assert pitch is not None and pitch > 20
	assert roll == 0


def test_gravity_wins_over_attitude():
	stamp = {'inertial': {'gravity': [3.802262, 9.020489, -0.640069]},
			 'attitude': {'pitch_deg': 40.0, 'roll_deg': -5.0, 'device_rotation_deg': 0},
			 'capture_timing': {'metadata_version': 3}}
	assert capture_pose(exif(stamp)) == pytest.approx((3.741, -22.856), abs=0.01)


def test_a_version_1_roll_180_off_gravity_is_overruled():
	stamp = {'inertial': {'gravity': [3.802262, 9.020489, -0.640069]},
			 'attitude': {'pitch_deg': -3.741, 'roll_deg': 22.856 - 180, 'device_rotation_deg': 0},
			 'capture_timing': {'metadata_version': 1}}
	assert capture_pose(exif(stamp)) == pytest.approx((3.741, -22.856), abs=0.01)


def test_a_half_turn_roll_fault_leaves_the_level_roll_alone():
	"""Without gravity, a version-1 row's 180° branch fault reduces to the same lean."""
	assert capture_pose(attitude(-3.741, 22.856 - 180, version=1)) == pytest.approx((3.741, -22.856), abs=0.01)


def test_old_portrait_rows_are_trusted():
	assert capture_pose(attitude(8.0, -6.0, rotation=0)) == (-8.0, 6.0)


@pytest.mark.parametrize('rotation', [90, 180, 270, None, '0'])
def test_old_rows_in_any_other_orientation_are_not(rotation):
	assert capture_pose(attitude(8.0, -6.0, rotation=rotation)) == (None, None)


def test_old_landscape_rows_count_once_versioned():
	assert capture_pose(attitude(8.0, 96.0, rotation=90, version=2)) == (-8.0, -6.0)


def test_rows_whose_gravity_is_null_fall_back_to_attitude():
	# 2026-09-28 to 10-01: a bug stamped the inertial object with a null gravity.
	stamp = {'inertial': {'gravity': None},
			 'attitude': {'pitch_deg': 8.0, 'roll_deg': -6.0, 'device_rotation_deg': 0}}
	assert capture_pose(exif(stamp)) == (-8.0, 6.0)
	assert capture_pose(exif({'inertial': {'gravity': None}})) == (None, None)


@pytest.mark.parametrize('g', [
	'9.8',
	{'x': 0, 'y': 9.8, 'z': 0},
	[0, 9.8],
	[0, 9.8, 0, 0],
	['0', '9.8', '0'],
	[True, 9.8, 0],
	[0, float('nan'), 0],
	[0, float('inf'), 0],
	[0, 0, 0],
])
def test_gravity_that_is_not_three_finite_numbers_is_ignored(g):
	assert capture_pose(gravity(g)) == (None, None)


@pytest.mark.parametrize('user_comment', [
	'Canon EOS 5DS R',
	'Canon\u0000\u0000',
	'{not json',
	'[1, 2, 3]',
	'{}',
	# The client outside this tree: a top-level pair holding the old landscape fault.
	'{"pitch": -84.25, "roll": -175.45}',
	None,
])
def test_comments_without_a_stamp_give_nothing(user_comment):
	assert capture_pose({'data': {'UserComment': user_comment}}) == (None, None)


@pytest.mark.parametrize('exif_data', [None, {}, {'data': None}, {'data': 'x'}, []])
def test_missing_exif_gives_nothing(exif_data):
	assert capture_pose(exif_data) == (None, None)


@pytest.mark.parametrize('pitch_deg,roll_deg', [
	(120.0, 0.0), (float('nan'), 0.0), ('5', 0.0), (None, 0.0), (True, 0.0),
])
def test_attitude_without_a_usable_pitch_gives_nothing(pitch_deg, roll_deg):
	assert capture_pose(attitude(pitch_deg, roll_deg, version=3)) == (None, None)


def test_attitude_without_a_usable_roll_keeps_its_pitch():
	assert capture_pose(attitude(8.0, None, version=3)) == (-8.0, None)
	assert capture_pose(attitude(8.0, 'level', version=3)) == (-8.0, None)


def test_near_flat_has_no_roll():
	"""Within about 15° of flat, the in-plane direction of gravity is a heading, not a lean."""
	pitch, roll = capture_pose(gravity([0.1, 0.1, 9.8]))
	assert pitch == pytest.approx(-89.17, abs=0.01)
	assert roll is None
	assert capture_pose(attitude(80.0, 30.0, version=3)) == (-80.0, None)
	# 74° from level still has a roll.
	assert capture_pose(attitude(74.0, 3.0, version=3))[1] == -3.0


@pytest.mark.parametrize('roll_deg,expected', [
	(0.0, 0.0),
	(10.0, -10.0),
	(-10.0, 10.0),
	(44.9, -44.9),
	(-44.9, 44.9),
	# The half-way points fall on +45 from either side, so the range is (-45, 45].
	(45.0, 45.0),
	(-45.0, 45.0),
	(135.0, 45.0),
	(-135.0, 45.0),
	(90.0, 0.0),
	(-90.0, 0.0),
	(180.0, 0.0),
	(-180.0, 0.0),
	(100.0, -10.0),
	(-100.0, 10.0),
])
def test_level_roll_is_measured_from_the_nearest_quarter_turn(roll_deg, expected):
	assert level_roll(roll_deg) == pytest.approx(expected, abs=1e-9)


def test_level_roll_never_returns_negative_zero():
	for roll_deg in (0.0, -0.0, 90.0, -90.0, 180.0, -180.0):
		assert math.copysign(1.0, level_roll(roll_deg)) == 1.0


def unstamped(gps_pitch, stamp=None) -> dict:
	"""exif_data as a frontend2 photo from before the attitude stamp has it."""
	return {'gps': {'pitch': gps_pitch, 'bearing': 120.0},
			'data': {'UserComment': json.dumps(stamp if stamp is not None else {'bearing_source': 'android-compass-true'})}}


def test_an_unstamped_portrait_photo_keeps_its_upload_pitch_negated():
	assert capture_pose(unstamped(12.5), 1440, 1920) == (-12.5, None)
	assert capture_pose(unstamped(-30), 1440, 1920) == (30.0, None)


@pytest.mark.parametrize('width,height', [(1920, 1440), (1440, 1440), (None, 1920), (1440, None), (0, 1920), ('1440', '1920')])
def test_the_upload_pitch_is_not_read_unless_the_image_is_portrait(width, height):
	# Landscape upload pitches carry that era's landscape fault: up to 97° off.
	assert capture_pose(unstamped(12.5), width, height) == (None, None)


def test_the_upload_pitch_is_not_read_without_dimensions():
	assert capture_pose(unstamped(12.5)) == (None, None)


@pytest.mark.parametrize('stamp', [
	# An attitude the rules reject (old landscape) came the same broken way as the pitch beside it.
	{'attitude': {'pitch_deg': 8.0, 'roll_deg': 96.0, 'device_rotation_deg': 270}},
	{'attitude': {'pitch_deg': 8.0, 'roll_deg': 186.0, 'device_rotation_deg': 180}},
	{'inertial': {'gravity': None}},
])
def test_the_upload_pitch_is_not_read_beside_a_stamp(stamp):
	assert capture_pose(unstamped(12.5, stamp), 1440, 1920) == (None, None)


def test_a_stamp_wins_over_the_upload_pitch():
	stamp = {'inertial': {'gravity': [3.802262, 9.020489, -0.640069]}}
	assert capture_pose(unstamped(40.0, stamp), 1440, 1920) == pytest.approx((3.741, -22.856), abs=0.01)


@pytest.mark.parametrize('gps_pitch', [None, '12.5', True, float('nan'), 91.0, -120.0])
def test_an_unusable_upload_pitch_is_ignored(gps_pitch):
	assert capture_pose(unstamped(gps_pitch), 1440, 1920) == (None, None)


def test_an_upload_pitch_without_any_user_comment_is_read():
	# The stamp is absent entirely: nothing contradicts the field.
	assert capture_pose({'gps': {'pitch': 5.0}}, 1440, 1920) == (-5.0, None)
	assert capture_pose({'gps': 'x'}, 1440, 1920) == (None, None)


# ── The shared fixture ──
# common/capture_pose_cases.json holds the cases this module, the web app's level
# indicator (capturePoseMath.ts) and frontend2 must agree on, with the gate limits.
# Its synthetic vectors were built from the pitch and roll they expect, not computed
# here. See docs/todo/web-capture-level-stamp.md.

CASES = json.loads((Path(__file__).resolve().parents[4] / 'common' / 'capture_pose_cases.json').read_text())


def _verdict(pitch, roll) -> str:
	"""The indicator's word for what the Panoramax pitch and roll gates will decide."""
	from panoramax.app.eligibility import MAX_PITCH_DEG, MAX_ROLL_DEG
	if roll is None:
		return 'flat'
	return 'level' if abs(pitch) <= MAX_PITCH_DEG and abs(roll) <= MAX_ROLL_DEG else 'tilted'


def test_the_fixture_limits_are_the_gates():
	from common.capture_pose import ROLL_FLOOR
	from panoramax.app.eligibility import MAX_PITCH_DEG, MAX_ROLL_DEG
	assert (CASES['max_pitch_deg'], CASES['max_roll_deg']) == (MAX_PITCH_DEG, MAX_ROLL_DEG)
	assert CASES['roll_floor'] == ROLL_FLOOR


@pytest.mark.parametrize('case', CASES['cases'] + CASES['deviceorientation'], ids=lambda c: c['id'])
def test_the_fixture_cases(case):
	pitch, roll = capture_pose(gravity(case['gravity']))
	assert pitch == pytest.approx(case['pitch'], abs=0.01)
	if case['roll'] is None:
		assert roll is None
	else:
		assert roll == pytest.approx(case['roll'], abs=0.01)
	assert _verdict(pitch, roll) == case['level']


# ── The web stamp ──
# The web app stamps `inertial` alone: no attitude, no capture_timing, no top-level
# pitch. Its gravity is GravitySensor's reading on Chromium (Android's TYPE_GRAVITY)
# or the up vector converted from deviceorientation's beta/gamma elsewhere, and the
# object carries keys frontend2's does not.

def web_stamp(g, source='deviceorientation') -> dict:
	return exif({'inertial': {'gravity': g, 'age_ms': 40, 'gravity_source': source,
							  'sample_count': 18, 'window_ms': 300, 'gravity_spread_deg': 0.8},
				 'location_source': 'map', 'bearing_source': 'map', 'location_accuracy_m': 1})


@pytest.mark.parametrize('case', CASES['deviceorientation'], ids=lambda c: c['id'])
def test_the_web_stamp_from_deviceorientation(case):
	pitch, roll = capture_pose(web_stamp(case['gravity']))
	assert pitch == pytest.approx(case['pitch'], abs=0.01)
	assert roll == (None if case['roll'] is None else pytest.approx(case['roll'], abs=0.01))


@pytest.mark.parametrize('g,pitch,roll', [p.values[:1] + p.values[4:] for p in REAL_ROWS])
def test_the_web_stamp_from_the_gravity_sensor(g, pitch, roll):
	"""Chromium's GravitySensor is TYPE_GRAVITY, so a frontend2 vector reads the same."""
	assert capture_pose(web_stamp(g, 'gravity-sensor')) == pytest.approx((pitch, roll), abs=0.01)


def test_the_web_stamps_extra_keys_change_nothing():
	g = [3.802262, 9.020489, -0.640069]
	assert capture_pose(web_stamp(g)) == capture_pose(gravity(g))


def test_a_web_stamp_never_reads_the_upload_pitch():
	# The web sends no top-level pitch, but if one rode along its inertial object
	# is a stamp, so the last resort stays shut.
	stamp = {'gps': {'pitch': 30.0}, **web_stamp([0.0, 9.80665, 0.0])}
	assert capture_pose(stamp, 1440, 1920) == (0.0, 0.0)
