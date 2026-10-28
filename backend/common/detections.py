"""Explicit stored blur decisions and normalization of incoming detections.

Every stored object has a boolean ``blurred`` flag after the production backfill.
Consumers read that decision directly. Confidence determines new writer decisions;
older incoming worker/precomputed payloads are normalized before use or storage.
Historical readers/verifiers live separately in common.legacy_detections.
"""

import math
from typing import Any, Dict, Optional


# Detections at or above this are actually blurred (and blacked out in the LLM
# variant). Below it they are recorded but left visible — see DETECT_CONFIDENCE
# in the worker's detections module for why the two thresholds are decoupled.
BLUR_CONFIDENCE = 0.4


def should_blur(obj) -> bool:
	"""Whether a recorded detection should actually be blurred/blacked out.

	Manual override rectangles carry no confidence and are always blurred;
	model detections are blurred at or above BLUR_CONFIDENCE. This computes a new
	write-side decision; consumers use is_blurred() to read the stored flag.
	Incoming legacy payloads use this rule during normalization only.
	"""
	conf = obj.get("confidence")
	return conf is None or conf >= BLUR_CONFIDENCE


def is_blurred(obj) -> bool:
	"""Read the stored decision; missing/non-boolean flags are errors."""
	flag = obj.get('blurred')
	if type(flag) is not bool:
		raise ValueError("Stored detection requires an explicit boolean 'blurred' flag")
	return flag


def normalize_detections(detected_objects: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
	"""Persist legacy reader decisions without changing any existing fields.

	Used at write boundaries and by the backfill. NULL, absent objects and empty
	arrays stay as supplied; malformed objects/flags/confidences raise ValueError.
	Coordinates are deliberately not repaired. Input dictionaries are never mutated.
	"""
	if detected_objects is None:
		return None
	if not isinstance(detected_objects, dict):
		raise ValueError('detected_objects must be an object or null')
	if 'objects' not in detected_objects:
		return detected_objects
	objects = detected_objects['objects']
	if not isinstance(objects, list):
		raise ValueError('detected_objects.objects must be an array')
	normalized = []
	changed = False
	for index, obj in enumerate(objects):
		if not isinstance(obj, dict):
			raise ValueError(f'detected_objects.objects[{index}] must be an object')
		if 'blurred' in obj and type(obj['blurred']) is not bool:
			raise ValueError(f'detected_objects.objects[{index}].blurred must be a boolean')
		confidence = obj.get('confidence')
		if confidence is not None and (
			type(confidence) not in (int, float) or not 0 <= confidence <= 1
			or not math.isfinite(confidence)
		):
			raise ValueError(f'detected_objects.objects[{index}].confidence must be a finite number in [0, 1]')
		if 'blurred' not in obj:
			obj = {**obj, 'blurred': should_blur(obj)}
			obj.setdefault('blurred_from', 'legacy-no-confidence' if confidence is None
			               else f'legacy-confidence-{BLUR_CONFIDENCE:g}')
			changed = True
		normalized.append(obj)
	return {**detected_objects, 'objects': normalized} if changed else detected_objects


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
