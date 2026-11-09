"""The blur verdict rule in common/image_quality.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from common.image_quality import (
	is_blurry, DEFOCUS_MAX_REL_P90, DEFOCUS_MAX_EDGE_P50, MOTION_MIN_X_WEAKER_SHARE, MOTION_MAX_AXIS_RATIO_P50,
)

SHARP_V2 = {"version": 2, "rel_p90": 5.0, "weak_rel_p50": 0.08, "weak_direction_agreement": 0.45,
			"edge_tiles": 300, "edge_p50": 0.34, "x_weaker_share": 0.5, "axis_ratio_p50": 0.8}
SHARP_V1 = {k: v for k, v in SHARP_V2.items() if not k.startswith(("edge", "x_", "axis"))} | {"version": 1}


def v2(**overrides):
	return {**SHARP_V2, **overrides}


def test_sharp_photo_is_not_blurry():
	assert is_blurry(SHARP_V2) is False
	assert is_blurry(SHARP_V1) is False


def test_defocus_needs_low_detail_and_wide_edges():
	assert is_blurry(v2(rel_p90=2.0, edge_p50=0.15)) is True
	# low contrast-relative detail but narrow edges: a clean, sparse-edged scene
	assert is_blurry(v2(rel_p90=2.0, edge_p50=0.25)) is False
	assert is_blurry(v2(rel_p90=DEFOCUS_MAX_REL_P90, edge_p50=0.15)) is False
	assert is_blurry(v2(rel_p90=2.0, edge_p50=DEFOCUS_MAX_EDGE_P50)) is False


def test_horizontal_smear_is_blurry():
	assert is_blurry(v2(x_weaker_share=1.0, axis_ratio_p50=0.5)) is True
	assert is_blurry(v2(x_weaker_share=MOTION_MIN_X_WEAKER_SHARE, axis_ratio_p50=0.6)) is True


@pytest.mark.parametrize("share, ratio", [
	(0.9, 0.4),                                  # not consistent enough
	(1.0, MOTION_MAX_AXIS_RATIO_P50),            # consistent but barely weaker
])
def test_motion_needs_both_signals(share, ratio):
	assert is_blurry(v2(x_weaker_share=share, axis_ratio_p50=ratio)) is False


def test_version_1_documents_keep_the_v1_rule():
	assert is_blurry(SHARP_V1 | {"rel_p90": 2.0}) is True
	assert is_blurry(SHARP_V1 | {"weak_direction_agreement": 0.9, "weak_rel_p50": 0.03}) is True


def test_v2_document_without_edge_tiles_judges_by_motion_only():
	doc = v2(rel_p90=2.0, edge_tiles=0)
	for key in ("edge_p50", "x_weaker_share", "axis_ratio_p50"):
		doc.pop(key)
	assert is_blurry(doc) is False


@pytest.mark.parametrize("sharpness", [None, {}, {"version": 2, "tiles_used": 0, "edge_tiles": 0}])
def test_nothing_to_judge_is_none(sharpness):
	assert is_blurry(sharpness) is None
