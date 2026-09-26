#!/usr/bin/env python3
"""Unit tests for `PhotoProcessor._validate_imu_samples`.

The raw IMU window is the ONLY client-supplied BULK artifact in the pipeline,
which is a combination that exists nowhere else here: everything else large is
produced by the worker from an image it decoded itself, and everything else
client-supplied is a handful of scalars the API bounds with
`_provenance_object`. So these checks are explicit, and so are their tests.

The payload's shape is produced by `imuSamplesPayloadJson` in shared-kt and
pinned on that side by `ImuPayloadTest`. See docs/recon-capture-metadata.md,
Phase 5.
"""
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from photo_processor import PhotoProcessor  # noqa: E402

validate = PhotoProcessor._validate_imu_samples


def block(n=3, t0_ms=1_700_000_000_000, t0_ns=812_340_000_000, step=2_500):
    """A well-formed sensor block: n samples, so n-1 gaps."""
    return {
        't0_ms': t0_ms, 't0_ns': t0_ns,
        'dt_us': [step] * (n - 1),
        'x': [0.1] * n, 'y': [0.2] * n, 'z': [9.8] * n,
    }


# --- the happy path ---

def test_a_well_formed_payload_survives_whole():
    out = validate({'accel': block(), 'gyro': block()})
    assert set(out) == {'accel', 'gyro'}
    assert out['accel']['t0_ms'] == 1_700_000_000_000
    assert out['accel']['t0_ns'] == 812_340_000_000
    assert out['accel']['dt_us'] == [2_500, 2_500]
    assert out['accel']['x'] == [0.1, 0.1, 0.1]


def test_a_single_sample_window_has_no_gaps():
    """n-1 gaps means ZERO gaps for one sample, not a missing field."""
    out = validate({'accel': block(n=1)})
    assert out['accel']['dt_us'] == []
    assert len(out['accel']['x']) == 1


def test_one_good_sensor_survives_a_broken_sibling():
    """A phone with a flaky gyroscope should still contribute its accelerometer."""
    out = validate({'accel': block(), 'gyro': {'x': 'nope'}})
    assert set(out) == {'accel'}


def test_integers_become_floats_so_a_column_has_one_type():
    out = validate({'accel': {**block(n=2), 'x': [1, 2], 'y': [0, 0], 'z': [9, 9]}})
    assert out['accel']['x'] == [1.0, 2.0]
    assert all(isinstance(v, float) for v in out['accel']['x'])


def test_the_monotonic_base_is_optional_but_the_wall_clock_is_not():
    """t0_ns is a bonus join key; t0_ms is how the window is found in time."""
    out = validate({'accel': {k: v for k, v in block().items() if k != 't0_ns'}})
    assert 't0_ns' not in out['accel']
    assert out['accel']['t0_ms'] == 1_700_000_000_000


# --- what must be rejected ---

def test_nothing_at_all_is_none_rather_than_an_empty_object():
    for bad in (None, {}, [], 'accel', 42):
        assert validate(bad) is None


def test_an_unknown_sensor_name_is_dropped():
    """This name becomes a key in a public artifact; the set is closed."""
    assert validate({'magnetometer': block()}) is None
    out = validate({'accel': block(), 'evil': block()})
    assert set(out) == {'accel'}


@pytest.mark.parametrize('axes', [
    {'x': [0.1], 'y': [0.1]},                       # z missing entirely
    {'x': [0.1, 0.2], 'y': [0.1, 0.2], 'z': [0.1]},  # ragged
    {'x': [], 'y': [], 'z': []},                    # says nothing
    {'x': 'not a list', 'y': [0.1], 'z': [0.1]},
    {'x': [[0.1]], 'y': [0.1], 'z': [0.1]},         # nested
    {'x': [None], 'y': [0.1], 'z': [0.1]},
    {'x': [True], 'y': [0.1], 'z': [0.1]},          # bool is an int subclass
    {'x': [float('nan')], 'y': [0.1], 'z': [0.1]},
    {'x': [float('inf')], 'y': [0.1], 'z': [0.1]},
])
def test_a_malformed_axis_set_drops_the_sensor(axes):
    n = max((len(v) for v in axes.values() if isinstance(v, list)), default=1)
    assert validate({'accel': {'t0_ms': 1, 'dt_us': [2_500] * (n - 1), **axes}}) is None


def test_ragged_is_rejected_rather_than_truncated():
    """A window whose x has 3 entries and y has 2 is not a 2-sample window, it
    is a bug upstream. Silently repairing it would hide that forever."""
    assert validate({'accel': {'t0_ms': 1, 'dt_us': [2_500, 2_500],
                               'x': [1.0, 2.0, 3.0], 'y': [1.0, 2.0], 'z': [1.0, 2.0, 3.0]}}) is None


@pytest.mark.parametrize('gaps', [
    None,
    'not a list',
    [2_500],              # one gap for three samples
    [2_500, 2_500, 2_500],  # three gaps for three samples
    [2_500, -1],          # time does not run backwards
    [2_500, True],        # bool is an int subclass
    [2_500, 2.5],         # microseconds are whole
])
def test_a_gap_count_or_type_mismatch_drops_the_sensor(gaps):
    """The n-1 contract is the encoder's; a mismatch means the two ends disagree
    about the encoding, which is worse than the window being absent."""
    assert validate({'accel': {**block(n=3), 'dt_us': gaps}}) is None


@pytest.mark.parametrize('t0', [None, 0, -1, 'now', 1.5, True])
def test_an_unusable_wall_clock_base_drops_the_sensor(t0):
    assert validate({'accel': {**block(), 't0_ms': t0}}) is None


def test_the_sample_count_is_capped_at_the_rings_capacity():
    """The cap is the capture buffer's size, not a byte figure: no honest window
    can exceed the ring that produced it."""
    cap = PhotoProcessor.IMU_MAX_SAMPLES_PER_SENSOR
    n = cap + 1
    assert validate({'accel': {'t0_ms': 1, 'dt_us': [2_500] * (n - 1),
                               'x': [0.1] * n, 'y': [0.1] * n, 'z': [0.1] * n}}) is None
    ok = validate({'accel': {'t0_ms': 1, 'dt_us': [2_500] * (cap - 1),
                             'x': [0.1] * cap, 'y': [0.1] * cap, 'z': [0.1] * cap}})
    assert len(ok['accel']['x']) == cap


def test_extra_keys_inside_a_sensor_block_do_not_ride_along():
    """Rebuilt key by key, not filtered in place — so a client cannot attach
    anything to a public artifact."""
    out = validate({'accel': {**block(), 'note': 'hello', 'w': [1.0, 2.0, 3.0]}})
    assert set(out['accel']) == {'t0_ms', 't0_ns', 'dt_us', 'x', 'y', 'z'}


# --- the cross-language contract ---

# Verbatim output of shared-kt's `imuSamplesPayloadJson`, as pinned by
# ImuPayloadTest.theShapeIsColumnarPerSensor. The two ends have no shared schema
# — the app hand-builds this string and the worker hand-checks it — so a literal
# is the contract. If the Kotlin test's expectation changes, this must change
# with it, and one of the two will fail first.
KOTLIN_PAYLOAD = (
    '{"accel":{"t0_ms":1700000000000,"t0_ns":812340000000,"dt_us":[2500],'
    '"x":[0.012,0.013],"y":[-1.5,-1.5],"z":[9.81,9.807]}}'
)


def test_the_apps_own_output_passes_the_door_unchanged():
    import json
    out = validate(json.loads(KOTLIN_PAYLOAD))
    assert out is not None, "the encoder's real output was rejected"
    assert out == {'accel': {
        't0_ms': 1700000000000, 't0_ns': 812340000000, 'dt_us': [2500],
        'x': [0.012, 0.013], 'y': [-1.5, -1.5], 'z': [9.81, 9.807],
    }}


def test_the_axis_and_gap_names_are_the_ones_the_app_writes():
    """Named separately from the round trip above: a rename on one side that
    happened to stay self-consistent would still break the other."""
    import json
    block = json.loads(KOTLIN_PAYLOAD)['accel']
    assert set(block) == {'t0_ms', 't0_ns', 'dt_us', 'x', 'y', 'z'}
    # ...and the n-1 gap contract holds in real output, not just in theory.
    assert len(block['dt_us']) == len(block['x']) - 1
