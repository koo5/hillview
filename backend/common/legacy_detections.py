"""Historical reader semantics for migration verification and old inventories.

Production consumers use the explicit flag via common.detections.is_blurred.
Keep this separate so old dumps and exact migration backups remain verifiable.
"""

# Pin the old rule independently of future writer threshold changes.
LEGACY_BLUR_CONFIDENCE = 0.4


def legacy_is_blurred(obj) -> bool:
	"""Reproduce the pre-backfill reader, including its eager confidence check."""
	confidence = obj.get('confidence')
	legacy_decision = confidence is None or confidence >= LEGACY_BLUR_CONFIDENCE
	return bool(obj.get('blurred', legacy_decision))


def _legacy_blurred_only(detected_objects):
	if not isinstance(detected_objects, dict) or not detected_objects.get('objects'):
		return detected_objects
	return {**detected_objects, 'objects': [o for o in detected_objects['objects'] if legacy_is_blurred(o)]}


def verify_detection_migration(before, after) -> None:
	"""Independently check representation, geometry and historical read verdicts."""
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
		require(legacy_is_blurred(old) == new['blurred'], 'blur verdict changed')
		projected.append({k: v for k, v in new.items() if k not in allowed})
	require(_legacy_blurred_only(before) == _legacy_blurred_only({**after, 'objects': projected}),
	        'public selection changed')
