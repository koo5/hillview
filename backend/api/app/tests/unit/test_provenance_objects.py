"""Unit tests for the `fix`, `lens` and `motion` provenance objects served by
GET /api/photos/public/{uid}.

`attitude` has its own file; the scalar coercion rules are tested there and
shared. What is new here is the LIST type — the lens calibration vectors and the
gravity/acceleration triples — which is the first provenance value that is not a
scalar, and therefore the first that could smuggle a large or ragged structure
into a public response.

Key names must match what the app emits (`fixProvenanceJson`,
`lensProvenanceJson`, `motionProvenanceJson`, pinned by frontend2's
`ProvenanceObjectsTest`). The worker between declares each object as an untyped
dict and passes it through whole, so THIS file and the Kotlin one are the two
that have to agree. See docs/recon-capture-metadata.md.
"""
import json
import os
import sys

import pytest

api_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(api_app_dir))
sys.path.insert(1, os.path.abspath(os.path.join(api_app_dir, '..', '..')))

from photo_routes import (  # noqa: E402
	_PROVENANCE_LIST_MAX,
	_PROVENANCE_STR_MAX,
	_fix,
	_lens,
	_inertial,
)


def exif(**objects):
	return {'data': {'UserComment': json.dumps({'location_source': 'gps', **objects})}}


# --- fix: error bars, never the position ---

def test_the_fix_object_carries_its_error_bars():
	out = _fix(exif(fix={
		'altitude_accuracy_m': 8.5, 'speed_mps': 1.4, 'speed_accuracy_mps': 0.3,
		'course_deg': 212.5, 'course_accuracy_deg': 15.0,
		'provider': 'fused', 'elected': True,
	}))
	assert out == {
		'altitude_accuracy_m': 8.5, 'speed_mps': 1.4, 'speed_accuracy_mps': 0.3,
		'course_deg': 212.5, 'course_accuracy_deg': 15.0,
		'provider': 'fused', 'elected': True,
	}


def test_a_lost_election_is_still_reported():
	"""A quality report about a fix the photo did NOT record is still useful —
	but a reader has to be able to tell which kind it is holding."""
	assert _fix(exif(fix={'speed_mps': 0.0, 'elected': False})) == {
		'speed_mps': 0.0, 'elected': False,
	}


def test_a_client_cannot_smuggle_a_position_into_the_fix_object():
	"""The position is already served at the top level. Anything else keyed
	here is a client inventing fields."""
	assert _fix(exif(fix={
		'latitude': 50.1, 'longitude': 14.4, 'accuracy_m': 4.2, 'speed_mps': 1.4,
	})) == {'speed_mps': 1.4}


# --- lens: the list type ---

FULL_LENS = {
	'focal_length_mm': 5.58,
	'aperture_f_stop': 1.79,
	'focus_distance_diopters': 0.0,
	'focus_distance_calibration': 'approximate',
	'focus_infinity_requested': True,
	'zoom_ratio': 2.0,
	'rolling_shutter_skew_ns': 33000000,
	'intrinsics': [1000.0, 1000.0, 960.0, 540.0, 0.0],
	'distortion': [0.1, -0.2, 0.01, 0.0, 0.0],
	'camera_intrinsics': [999.0, 999.0, 961.0, 541.0, 0.0],
	'camera_distortion': [0.1, -0.2, 0.0, 0.0, 0.0],
	'sensor_physical_size_mm': [5.6, 4.2],
	'sensor_pixel_array': [4000, 3000],
	'intrinsics_available': True,
}


def test_every_lens_field_survives():
	out = _lens(exif(lens=FULL_LENS))
	assert out == FULL_LENS


def test_zoom_is_kept_because_it_changes_the_intrinsics():
	"""The app has had pinch-to-zoom for as long as it has had a camera, and
	recorded nothing: a frame shot at 2x whose intrinsics are read as the 1x
	ones is simply wrong."""
	assert _lens(exif(lens={'zoom_ratio': 2.0}))['zoom_ratio'] == 2.0


def test_an_absent_calibration_is_a_recorded_fact():
	"""False must survive. "This phone publishes no calibration" and "this app
	version did not look" are different claims, and only one is the phone's
	fault."""
	assert _lens(exif(lens={'intrinsics_available': False})) == {'intrinsics_available': False}


def test_focus_at_infinity_is_zero_diopters_not_a_missing_value():
	"""0.0 IS infinity in the platform's unit. A truthiness check would drop
	exactly the value this app's landscape photography cares about."""
	out = _lens(exif(lens={'focus_distance_diopters': 0.0, 'focus_infinity_requested': True}))
	assert out == {'focus_distance_diopters': 0.0, 'focus_infinity_requested': True}


@pytest.mark.parametrize('bad', [
	{'intrinsics': 'not a list'},
	{'intrinsics': []},                                   # says nothing
	{'intrinsics': [1.0, 'two', 3.0]},                    # ragged
	{'intrinsics': [1.0, None]},
	{'intrinsics': [1.0, float('nan')]},                  # not JSON-representable
	{'intrinsics': [1.0, True]},                          # bool is an int subclass
	{'intrinsics': [[1.0], [2.0]]},                       # nested
	{'intrinsics': {'fx': 1000}},
])
def test_a_ragged_or_wrong_typed_vector_is_dropped(bad):
	assert _lens(exif(lens=bad)) is None


def test_a_vector_cannot_be_unbounded():
	"""An intrinsic matrix is five numbers, not fifty thousand. This response is
	public and the UserComment is client-written."""
	assert _lens(exif(lens={'intrinsics': [1.0] * (_PROVENANCE_LIST_MAX + 1)})) is None
	ok = _lens(exif(lens={'intrinsics': [1.0] * _PROVENANCE_LIST_MAX}))
	assert len(ok['intrinsics']) == _PROVENANCE_LIST_MAX


def test_integers_in_a_vector_become_floats_consistently():
	"""One vector must not arrive as a mix of ints and floats depending on
	whether a value happened to be whole."""
	out = _lens(exif(lens={'sensor_pixel_array': [4000, 3000]}))
	assert out['sensor_pixel_array'] == [4000.0, 3000.0]
	assert all(isinstance(v, float) for v in out['sensor_pixel_array'])


def test_the_lens_string_field_is_length_capped():
	out = _lens(exif(lens={'focus_distance_calibration': 'x' * 500}))
	assert out == {'focus_distance_calibration': 'x' * _PROVENANCE_STR_MAX}


# --- motion ---

def test_the_inertial_object_carries_gravity_and_the_blur_signal():
	out = _inertial(exif(inertial={
		'gravity': [0.0, 0.0, 9.81],
		'linear_acceleration': [3.0, 4.0, 0.0],
		'linear_acceleration_magnitude': 5.0,
		'age_ms': 40,
	}))
	assert out['gravity'] == [0.0, 0.0, 9.81]
	assert out['linear_acceleration_magnitude'] == 5.0
	assert out['age_ms'] == 40


def test_a_stationary_phone_reads_as_zero_motion_not_as_absent():
	"""0 is the most informative value this field takes — it says the frame was
	shot from a standing phone, which is the one a reconstruction wants most."""
	out = _inertial(exif(inertial={'linear_acceleration_magnitude': 0.0, 'age_ms': 0}))
	assert out == {'linear_acceleration_magnitude': 0.0, 'age_ms': 0}


# --- the nested IMU window, the only nested object so far ---

def test_the_imu_window_nests_inside_inertial():
	out = _inertial(exif(inertial={
		'gravity': [0.0, 0.0, 9.81],
		'imu_window': {
			'sample_count': 104,
			'window_start_ms': 1700000000000,
			'window_end_ms': 1700000001000,
			'stored_count': 61,
			'accel_peak_mps2': 10.4,
			'accel_peak_deviation_mps2': 0.6,
			'gyro_peak_rad_s': 0.12,
		},
	}))
	assert out['imu_window']['sample_count'] == 104
	# What span the summary covers. The samples themselves travel as their own
	# gzipped artifact (photos.imu_samples_url), never through this object.
	assert out['imu_window']['window_start_ms'] == 1700000000000
	assert out['imu_window']['gyro_peak_rad_s'] == 0.12
	# What this capture ADDED, as opposed to what it spanned — the on-device
	# trim makes consecutive interval windows tile rather than repeat, and a
	# reader concatenating a run needs to know which number is which.
	assert out['imu_window']['stored_count'] == 61


def test_a_window_that_stored_nothing_reports_zero():
	"""The normal case in a fast interval run: the previous photo's window
	already covered this one. 0 is a measurement, not an absence."""
	out = _inertial(exif(inertial={'imu_window': {'sample_count': 104, 'stored_count': 0}}))
	assert out == {'imu_window': {'sample_count': 104, 'stored_count': 0}}


def test_the_window_rejects_unknown_and_wrongly_typed_inner_keys():
	out = _inertial(exif(inertial={'imu_window': {
		'sample_count': 104,
		'evil': {'deeper': [1, 2, 3]},
		'accel_peak_mps2': 'loud',
		'gyro_peak_rad_s': float('inf'),
	}}))
	assert out == {'imu_window': {'sample_count': 104}}


@pytest.mark.parametrize('bad', [
	{'imu_window': 'not a dict'},
	{'imu_window': []},
	{'imu_window': {}},
	{'imu_window': {'unknown_only': 1}},
	# One level of nesting, by design: unbounded depth is a way to smuggle size
	# into a public response.
	{'imu_window': {'imu_window': {'sample_count': 1}}},
])
def test_a_malformed_window_is_dropped_without_taking_the_object_with_it(bad):
	assert _inertial(exif(inertial=bad)) is None
	# ...and a good sibling still survives alongside a bad window.
	out = _inertial(exif(inertial={**bad, 'linear_acceleration_magnitude': 5.0}))
	assert out == {'linear_acceleration_magnitude': 5.0}


def test_a_window_with_no_point_sample_still_travels():
	"""A device with no gravity sensor can still have an accelerometer."""
	out = _inertial(exif(inertial={'imu_window': {'sample_count': 12}}))
	assert out == {'imu_window': {'sample_count': 12}}


# --- shared: absence ---

@pytest.mark.parametrize('reader', [_fix, _lens, _inertial])
@pytest.mark.parametrize('exif_data', [
	None,
	{},
	{'data': {'UserComment': 'Shot on a phone'}},
	{'data': {'UserComment': '{bad json'}},
])
def test_absent_or_malformed_is_none_for_every_object(reader, exif_data):
	assert reader(exif_data) is None


@pytest.mark.parametrize('reader,name', [(_fix, 'fix'), (_lens, 'lens'), (_inertial, 'inertial')])
def test_only_unknown_keys_is_none_not_an_empty_object(reader, name):
	assert reader(exif(**{name: {'made_up': 1}})) is None


def test_the_objects_do_not_read_each_others_keys():
	"""Each projection reads its OWN object. A key in the wrong one is a client
	mistake or a rename half-applied, and must not be silently honoured."""
	assert _lens(exif(fix={'zoom_ratio': 2.0})) is None
	assert _fix(exif(lens={'speed_mps': 1.4})) is None
	assert _inertial(exif(lens={'gravity': [0.0, 0.0, 9.81]})) is None
