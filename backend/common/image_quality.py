"""The blur verdict: photos.blurry, derived from image_metrics.sharpness.

Pure and dependency-free, so the worker (which measures) and the backfill
script (which classifies stored numbers) share one rule. Retuning means
editing the thresholds here, bumping BLUR_RULE_VERSION and re-running
image_metrics_backfill.py classify; nothing is re-measured unless the rule
needs a field the stored documents lack.

What "blurry" is for: hiding low-quality phone material from the map —
frames smeared by a moving photographer or a swinging camera, frames with
nothing in focus. A sharp subject against a blurred background (shallow depth
of field, a paddle swinging past) is NOT blurry.

Rule v2 (sharpness documents of version 2, 2026-11-03):

- defocus: nothing is sharp (rel_p90) AND the edges are wide (edge_p50).
  Contrast-relative energy alone flagged clean, sparse-edged phone shots — a
  wall, a bin, mesh, dotted glass — that the user reviewed as fine; their
  edges are narrow.
- motion: nearly every edge tile has its horizontal slope weaker
  (x_weaker_share) and markedly so (axis_ratio_p50). Rule v1's "most tiles
  share a weak direction" missed frames the user marked as smeared, at
  agreement 0.98-1.00 but just over its detail bound.

On the user's review set (25 photos rule v1 wrongly flagged, 8 it missed)
plus 5 known blurry: v2 flags 5/25 of the first (a partly smeared foreground
under a sharp building, railway rails whose horizontal edges are structural,
a dim underpass, a text close-up), 6/8 of the second (missed: one frame whose
burned-in text is sharp, accepted), 5/5 known; 9% of a random 400.

Rule v1 (any sharpness document without the edge fields): nothing in focus
(rel_p90 < 2.5) or a consistent one-directional smear (agreement > 0.85,
weak_rel_p50 < 0.04). Kept so a re-measure in progress leaves no photo
unjudged.
"""

from typing import Any, Mapping, Optional

BLUR_RULE_VERSION = 2

DEFOCUS_MAX_REL_P90 = 2.5
DEFOCUS_MAX_EDGE_P50 = 0.21
MOTION_MIN_X_WEAKER_SHARE = 0.95
MOTION_MAX_AXIS_RATIO_P50 = 0.65

# rule v1, for documents measured before the edge fields existed
V1_MOTION_MIN_AGREEMENT = 0.85
V1_MOTION_MAX_WEAK_REL_P50 = 0.04


def is_blurry(sharpness: Optional[Mapping[str, Any]]) -> Optional[bool]:
	"""The verdict for one image_metrics.sharpness document; None when there is nothing to judge."""
	if not sharpness or sharpness.get("rel_p90") is None:
		return None   # unmeasured, or no textured tiles at all (fog, black frames)
	if "edge_p50" not in sharpness and "edge_tiles" not in sharpness:
		return _is_blurry_v1(sharpness)
	if sharpness["rel_p90"] < DEFOCUS_MAX_REL_P90 and sharpness.get("edge_p50") is not None \
			and sharpness["edge_p50"] < DEFOCUS_MAX_EDGE_P50:
		return True
	share, ratio = sharpness.get("x_weaker_share"), sharpness.get("axis_ratio_p50")
	return share is not None and ratio is not None \
		and share >= MOTION_MIN_X_WEAKER_SHARE and ratio < MOTION_MAX_AXIS_RATIO_P50


def _is_blurry_v1(sharpness: Mapping[str, Any]) -> bool:
	if sharpness["rel_p90"] < DEFOCUS_MAX_REL_P90:
		return True
	agreement = sharpness.get("weak_direction_agreement")
	weak = sharpness.get("weak_rel_p50")
	return agreement is not None and weak is not None \
		and agreement > V1_MOTION_MIN_AGREEMENT and weak < V1_MOTION_MAX_WEAK_REL_P50
