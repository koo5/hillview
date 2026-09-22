"""The stored shape of ``Photo.detected_objects``, and how to read it back.

The worker writes this column (``anonymize.py``, ``photo_processor.py``); the
API serves it (``get_photo_detections``). Both have to reach the same verdict
on "was this box actually blurred?" across the four formats that coexist in the
DB, so the threshold and the legacy fallback live here rather than in either
container on its own.

Write-side knobs — the detector's own floor, the target class list, the blur
kernel sizes — stay in the worker's ``detections`` module, which re-exports
what is here so its own callers read as before.
"""

from typing import Any, Dict, Optional


# Detections at or above this are actually blurred (and blacked out in the LLM
# variant). Below it they are recorded but left visible — see DETECT_CONFIDENCE
# in the worker's detections module for why the two thresholds are decoupled.
BLUR_CONFIDENCE = 0.4


# detected_objects schema — FOUR variants coexist in the DB, in order of recency:
#   1.  Oldest model detections: {class_id, class_name, blur, bbox} — NO confidence,
#       scale, or blurred flag. should_blur() sees no confidence and treats them as
#       always-blurred, matching how they were processed at the time.
#   1b. Model detections WITH "confidence" + "scale" but still NO "blurred" flag (the
#       intermediate format). should_blur() correctly re-derives the decision from the
#       stored confidence (>= BLUR_CONFIDENCE). - the threshold may have moved a fer
#       times before settling on 0.4.
#   2.  Current model detections (anonymize.py): 1b + an explicit "blurred" bool
#       (= should_blur at write time), so consumers needn't re-derive anything.
#   3.  Manual overrides (photo_processor.py, container also carries "manual": True):
#       rects with class_id=None, no confidence, blur=500, "blurred": True — always
#       blurred.
# Consumer convention: `obj.get("blurred", should_blur(obj))` — uses the persisted flag
# for #2/#3 and falls back to should_blur() for #1 (always-blur) and #1b (from conf).
def should_blur(obj) -> bool:
	"""Whether a recorded detection should actually be blurred/blacked out.

	Manual override rectangles carry no confidence and are always blurred;
	model detections are blurred at or above BLUR_CONFIDENCE. Prefer the persisted
	`blurred` flag where present (formats #2/#3 above); this re-derives it for the
	legacy format #1 that predates the flag.
	"""
	conf = obj.get("confidence")
	return conf is None or conf >= BLUR_CONFIDENCE


def is_blurred(obj) -> bool:
	"""The consumer convention above, as one callable."""
	return bool(obj.get("blurred", should_blur(obj)))


def blurred_only(detected_objects: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
	"""``detected_objects`` with only the boxes that were actually blurred.

	What a caller who is not the owner gets. The recorded-but-unblurred boxes —
	the sub-threshold band between DETECT_CONFIDENCE and BLUR_CONFIDENCE — are a
	machine-readable index of people the detector saw and the pipeline chose to
	leave visible; the blurred image itself does not hand that out, and neither
	should the API.

	The container's own keys (model_name, manual) are kept: they describe the
	pass, not its subjects.
	"""
	if not isinstance(detected_objects, dict):
		return detected_objects
	objects = detected_objects.get("objects")
	if not objects:
		return detected_objects
	return {**detected_objects, "objects": [o for o in objects if is_blurred(o)]}
