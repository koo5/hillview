"""Unit tests for the device attitude served by GET /api/photos/public/{uid}.

What the DEVICE measured at the shutter — heading, pitch, ROLL and the quality
of each. It reaches the server inside the UserComment provenance, which the
capture app writes (or the worker synthesizes from metadata the app sent), so
the server's job here is a TYPED PROJECTION: only known keys, only expected
types, and a length cap on the one string. Anything else would let a client put
arbitrary JSON of arbitrary size into a public response.

It is public on OTHER people's photos deliberately — a 3-D reconstruction that
can only use the caller's own frames reconstructs nowhere — which is the same
reasoning that made ``location_accuracy_m`` public, and ``bearing`` always was.

The key names here must match what the app emits (``attitudeProvenanceJson``,
pinned by frontend2's ``AttitudeProvenanceTest``). The worker in between
declares only the OUTER ``attitude`` key and passes the object through whole,
so it needs no edit when an inner name changes — which means THIS file and the
Kotlin one are the two that have to agree. A name changed on one side only is a
field that reaches the database and is never served.
"""
import json
import os
import sys

import pytest

# api/app on the path so route modules import the same way the app does;
# backend root for ``common``.
api_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(api_app_dir))
sys.path.insert(1, os.path.abspath(os.path.join(api_app_dir, '..', '..')))

from photo_routes import _ATTITUDE_FUSION_MAX, _attitude  # noqa: E402


def exif(attitude):
	"""An exif_data dict carrying ``attitude`` in the UserComment, as the
	worker's synthesized provenance and the app's EXIF writer both produce."""
	return {'data': {'UserComment': json.dumps({
		'location_source': 'gps',
		'bearing_source': 'arrow_drag',
		'attitude': attitude,
	})}}


FULL = {
	'heading_true_deg': 68.5,
	'heading_magnetic_deg': 64.25,
	'pitch_deg': 4.75,
	'roll_deg': -1.5,
	'magnetometer_calibration': 3,
	'fused_sensor_accuracy': 2,
	'fusion': 'UPRIGHT_ROTATION_VECTOR (EMA smoothed)',
	'age_ms': 0,
	'device_rotation_deg': 90,
	'landscape_azimuth_negation': False,
}


def test_every_field_the_app_sends_survives():
	assert _attitude(exif(FULL)) == FULL


def test_roll_is_there_because_nothing_else_carries_it():
	"""Roll's only route off the phone. The sensor stack has computed it from
	the beginning and no field anywhere in the chain carried it until
	2026-09-22, so this is the assertion that matters most."""
	assert _attitude(exif({'roll_deg': -1.5}))['roll_deg'] == -1.5


def test_the_two_accuracies_are_separate_facts():
	"""One is the magnetometer's latched calibration, the other the fused
	sample's own self-rating. Neither may stand in for the other."""
	only_mag = _attitude(exif({'magnetometer_calibration': 0}))
	assert only_mag == {'magnetometer_calibration': 0}
	only_fused = _attitude(exif({'fused_sensor_accuracy': 3}))
	assert only_fused == {'fused_sensor_accuracy': 3}


def test_a_zero_reading_is_kept_not_dropped_as_falsy():
	"""0 means "the magnetometer called itself unreliable", which is the single
	most useful value in the field. A truthiness check would lose it."""
	out = _attitude(exif({
		'magnetometer_calibration': 0, 'age_ms': 0, 'roll_deg': 0.0,
		'device_rotation_deg': 0, 'landscape_azimuth_negation': False,
	}))
	assert out == {
		'magnetometer_calibration': 0, 'age_ms': 0, 'roll_deg': 0.0,
		'device_rotation_deg': 0, 'landscape_azimuth_negation': False,
	}


# --- the projection is a filter, not a pass-through ---

def test_unknown_keys_never_reach_the_response():
	"""The UserComment is client-written, and this response is PUBLIC."""
	out = _attitude(exif({
		'roll_deg': -1.5,
		'evil': {'nested': [1, 2, 3]},
		'<script>': 'x',
		'device_id': 'IMEI-12345',
	}))
	assert out == {'roll_deg': -1.5}


def test_the_one_string_is_length_capped():
	out = _attitude(exif({'fusion': 'x' * 5000}))
	assert out == {'fusion': 'x' * _ATTITUDE_FUSION_MAX}


@pytest.mark.parametrize('bad', [
	{'heading_true_deg': '68.5'},          # a number as a string
	{'heading_true_deg': float('nan')},    # not JSON-representable
	{'heading_true_deg': float('inf')},
	{'pitch_deg': [1, 2]},
	{'pitch_deg': {'a': 1}},
	{'fusion': 123},                       # the string field, not a string
	{'fusion': ''},                        # empty says nothing
	{'device_rotation_deg': True},         # bool is an int subclass in Python
	{'landscape_azimuth_negation': 1},     # truthy, but not a measurement
	{'landscape_azimuth_negation': 'yes'},
])
def test_wrong_types_are_dropped_rather_than_coerced(bad):
	"""Coercing would publish a claim the device never made — True as a
	rotation of 1 degree, or a truthy 1 as "the workaround was on"."""
	assert _attitude(exif(bad)) is None


@pytest.mark.parametrize('exif_data', [
	None,
	{},
	{'data': {}},
	{'data': {'UserComment': 'Shot on a phone'}},        # someone's free text
	{'data': {'UserComment': '{bad json'}},
	{'data': {'UserComment': json.dumps({'attitude': 'not a dict'})}},
	{'data': {'UserComment': json.dumps({'attitude': []})}},
	{'data': {'UserComment': json.dumps({'attitude': {}})}},
	{'data': {'UserComment': json.dumps({'location_source': 'gps'})}},  # no attitude
])
def test_absent_or_malformed_is_none(exif_data):
	"""None, not {} — every photo taken before the app recorded this has no
	attitude at all, and the response should say so rather than imply an
	empty measurement."""
	assert _attitude(exif_data) is None


def test_only_unknown_keys_is_none_not_an_empty_object():
	assert _attitude(exif({'made_up': 1})) is None


def test_integers_stay_integers_and_floats_stay_floats():
	"""The scales differ: calibration is 0..3, an angle is continuous. A float
	calibration of 2.7 is not a grade the platform ever reports."""
	out = _attitude(exif({'magnetometer_calibration': 2.7, 'roll_deg': 3}))
	assert out['magnetometer_calibration'] == 2
	assert isinstance(out['magnetometer_calibration'], int)
	assert out['roll_deg'] == 3.0
	assert isinstance(out['roll_deg'], float)
