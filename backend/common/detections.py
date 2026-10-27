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

import math
from typing import Any, Dict, Optional


# Detections at or above this are actually blurred (and blacked out in the LLM
# variant). Below it they are recorded but left visible — see DETECT_CONFIDENCE
# in the worker's detections module for why the two thresholds are decoupled.
BLUR_CONFIDENCE = 0.4


# detected_objects reader cases (writer history: docs/todo/detections-format-migration.md):
#   1.  Oldest model detections: {class_id, class_name, blur, bbox} — NO confidence,
#       scale, or blurred flag. should_blur() sees no confidence and treats them as
#       always-blurred. Old writers attempted to paint every stored box; this is
#       not a guarantee that its coordinates match the rendered pixels.
#   1b. Model detections WITH "confidence" + "scale" but still NO "blurred" flag (the
#       intermediate format). should_blur() correctly re-derives the decision from the
#       stored confidence (>= BLUR_CONFIDENCE). Confidence storage began 2026-06-12
#       with a detector floor of 0.4; the split record/paint thresholds followed
#       2026-06-13. No later blur-threshold change was found in this history.
#   2.  Current model detections (anonymize.py): 1b + an explicit "blurred" bool
#       (= should_blur at write time), so consumers needn't re-derive anything.
#   3.  Manual overrides (photo_processor.py, container also carries "manual": True):
#       rects with class_id=None, no confidence, blur=500, "blurred": True — always
#       blurred. Manual rectangles existed WITHOUT the flag from 2026-02-14
#       until it was added for both model and manual objects on 2026-06-24.
# Consumer convention: `obj.get("blurred", should_blur(obj))` — uses the persisted flag
# for #2/#3 and falls back to should_blur() for #1 (always-blur) and #1b (from conf).
def should_blur(obj) -> bool:
	"""Whether a recorded detection should actually be blurred/blacked out.

	Manual override rectangles carry no confidence and are always blurred;
	model detections are blurred at or above BLUR_CONFIDENCE. This computes a new
	write-side decision; consumers should use is_blurred() to prefer an existing
	flag and fall back to this rule only for legacy entries.
	"""
	conf = obj.get("confidence")
	return conf is None or conf >= BLUR_CONFIDENCE


def is_blurred(obj) -> bool:
	"""The consumer convention above, as one callable."""
	return bool(obj.get("blurred", should_blur(obj)))


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


def verify_detection_migration(before, after) -> None:
	"""Independent representation/reader invariants; raises on any unexpected edit.

	Only a missing flag and missing provenance may be added. In particular, an
	existing flag or provenance cannot be overwritten, and box order is significant.
	This is intentionally separate from the transformation used by the migration.
	"""
	def require(condition, message):
		if not condition:
			raise ValueError(f'Detection migration verification failed: {message}')

	if before is None or not isinstance(before, dict) or not before.get('objects'):
		require(before == after, 'empty value changed')
		return
	require(isinstance(after, dict), 'container type changed')
	require({k: v for k, v in before.items() if k != 'objects'} ==
	        {k: v for k, v in after.items() if k != 'objects'}, 'container fields changed')
	old_objects, new_objects = before['objects'], after.get('objects')
	require(isinstance(new_objects, list) and len(old_objects) == len(new_objects), 'object count changed')
	projected = []
	for old, new in zip(old_objects, new_objects):
		require(isinstance(new, dict) and type(new.get('blurred')) is bool, 'missing boolean flag')
		if 'blurred' not in old:
			require('blurred_from' in new, 'missing provenance for derived flag')
		allowed = {'blurred', 'blurred_from'} - old.keys()
		require(set(new) - set(old) <= allowed, 'unexpected object field added')
		require(all(k in new and new[k] == v for k, v in old.items()), 'existing object field changed')
		require(is_blurred(old) == new['blurred'], 'blur verdict changed')
		projected.append({k: v for k, v in new.items() if k not in allowed})
	require(blurred_only(before) == blurred_only({**after, 'objects': projected}), 'public selection changed')


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
