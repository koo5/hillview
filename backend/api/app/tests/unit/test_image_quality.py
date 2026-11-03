"""The blur verdict rule in common/image_quality.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from common.image_quality import is_blurry, DEFOCUS_MAX_REL_P90, MOTION_MIN_AGREEMENT, MOTION_MAX_WEAK_REL_P50

SHARP = {"version": 1, "rel_p90": 5.0, "weak_rel_p50": 0.08, "weak_direction_agreement": 0.45}


def doc(**overrides):
	return {**SHARP, **overrides}


def test_sharp_photo_is_not_blurry():
	assert is_blurry(SHARP) is False


def test_nothing_in_focus_is_blurry():
	assert is_blurry(doc(rel_p90=DEFOCUS_MAX_REL_P90 - 0.01)) is True
	assert is_blurry(doc(rel_p90=DEFOCUS_MAX_REL_P90)) is False


def test_consistent_one_directional_smear_is_blurry():
	assert is_blurry(doc(weak_direction_agreement=0.9, weak_rel_p50=0.03)) is True


@pytest.mark.parametrize("agreement, weak", [
	(MOTION_MIN_AGREEMENT, 0.03),          # agreement must exceed the threshold
	(0.9, MOTION_MAX_WEAK_REL_P50),        # detail must be below it
	(0.6, 0.02),                           # weak but not consistent: structure, not smear
	(0.95, 0.07),                          # consistent but plenty of detail left
])
def test_motion_needs_both_signals(agreement, weak):
	assert is_blurry(doc(weak_direction_agreement=agreement, weak_rel_p50=weak)) is False


@pytest.mark.parametrize("sharpness", [None, {}, {"version": 1, "tiles_used": 0}])
def test_nothing_to_judge_is_none(sharpness):
	assert is_blurry(sharpness) is None
