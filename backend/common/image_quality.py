"""The blur verdict: photos.blurry, derived from image_metrics.sharpness.

Pure and dependency-free, so the worker (which measures) and the backfill
script (which classifies stored numbers) share one rule. Retuning means
editing the thresholds here, bumping BLUR_RULE_VERSION and re-running
image_metrics_backfill.py classify; nothing is re-measured.

What "blurry" is for: hiding low-quality phone material from the map —
frames smeared by a moving photographer or a swinging camera, frames with
nothing in focus. A sharp subject against a blurred background (shallow depth
of field, a paddle swinging past) is NOT blurry. Hence:

- defocus: even the sharpest tenth of the tiles is soft (rel_p90). The median
  (rel_p50) was tried first and flagged telephoto shots with a sharp subject
  on bokeh.
- motion: most tiles lose their detail along the same direction
  (weak_direction_agreement) and the weakest direction has little left
  (weak_rel_p50).

Calibrated 2026-11-03 on the 97k backfilled photos to the ~10% the user
estimated: this rule flags 9.5%. Contact sheets just inside both thresholds
were mostly true blur; the known false positives are curated Canon telephoto
frames of smooth surfaces against bokeh (3.4% of 566), which phones rarely
produce.
"""

from typing import Any, Mapping, Optional

BLUR_RULE_VERSION = 1

DEFOCUS_MAX_REL_P90 = 2.5
MOTION_MIN_AGREEMENT = 0.85
MOTION_MAX_WEAK_REL_P50 = 0.04


def is_blurry(sharpness: Optional[Mapping[str, Any]]) -> Optional[bool]:
	"""The verdict for one image_metrics.sharpness document; None when there is nothing to judge."""
	if not sharpness or sharpness.get("rel_p90") is None:
		return None   # unmeasured, or no textured tiles at all (fog, black frames)
	if sharpness["rel_p90"] < DEFOCUS_MAX_REL_P90:
		return True
	agreement = sharpness.get("weak_direction_agreement")
	weak = sharpness.get("weak_rel_p50")
	return agreement is not None and weak is not None and agreement > MOTION_MIN_AGREEMENT and weak < MOTION_MAX_WEAK_REL_P50
