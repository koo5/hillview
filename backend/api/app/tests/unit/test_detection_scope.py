"""Unit tests for who sees which anonymization boxes on GET /photos/{id}/detections.

The column records every detection from DETECT_CONFIDENCE up, but only the ones
at BLUR_CONFIDENCE and above were painted over. The recorded-but-unblurred band
is therefore a list of people the pipeline saw and deliberately left visible —
the owner and moderators may read it (it is what the threshold gets re-tuned
from), nobody else may.
"""
import os
import sys

import pytest
from unittest.mock import AsyncMock, Mock

# api/app on the path so route modules import the same way the app does;
# backend root for ``common``.
api_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(api_app_dir))
sys.path.insert(1, os.path.abspath(os.path.join(api_app_dir, '..', '..')))

from common.detections import BLUR_CONFIDENCE, blurred_only, is_blurred, should_blur  # noqa: E402
from common.models import UserRole  # noqa: E402
from photo_routes import ProcessedPhotoData, get_photo_detections  # noqa: E402

OWNER_ID = 'owner-1'

# Legacy examples are incoming worker payloads, not valid stored objects.
LEGACY = {'class_id': 0, 'class_name': 'person', 'blur': 151, 'bbox': {'x1': 0, 'y1': 0, 'x2': 9, 'y2': 9}}
CONF_HIGH = {'class_id': 2, 'class_name': 'car', 'confidence': 0.9, 'scale': 1.0, 'bbox': {'x1': 1, 'y1': 1, 'x2': 9, 'y2': 9}}
CONF_LOW = {'class_id': 0, 'class_name': 'person', 'confidence': 0.3, 'scale': 0.5, 'bbox': {'x1': 2, 'y1': 2, 'x2': 9, 'y2': 9}}
FLAGGED_ON = {'class_id': 7, 'class_name': 'truck', 'confidence': 0.1, 'blurred': True, 'bbox': {'x1': 3, 'y1': 3, 'x2': 9, 'y2': 9}}
FLAGGED_OFF = {'class_id': 0, 'class_name': 'person', 'confidence': 0.99, 'blurred': False, 'bbox': {'x1': 4, 'y1': 4, 'x2': 9, 'y2': 9}}
MANUAL = {'class_id': None, 'blur': 500, 'blurred': True, 'bbox': {'x1': 5, 'y1': 5, 'x2': 9, 'y2': 9}}

INCOMING_OBJECTS = [LEGACY, CONF_HIGH, CONF_LOW, FLAGGED_ON, FLAGGED_OFF, MANUAL]
INCOMING = {'objects': INCOMING_OBJECTS, 'model_name': 'yolo11x.pt'}
ALL_OBJECTS = [
	{**LEGACY, 'blurred': True, 'blurred_from': 'legacy-no-confidence'},
	{**CONF_HIGH, 'blurred': True, 'blurred_from': 'legacy-confidence-0.4'},
	{**CONF_LOW, 'blurred': False, 'blurred_from': 'legacy-confidence-0.4'},
	FLAGGED_ON, FLAGGED_OFF, MANUAL,
]
BLURRED_OBJECTS = [ALL_OBJECTS[0], ALL_OBJECTS[1], FLAGGED_ON, MANUAL]

DETECTED = {'objects': ALL_OBJECTS, 'model_name': 'yolo11x.pt'}


class TestWorkerDetectionsWriteBoundary:
	def test_old_worker_payload_gets_explicit_flags_without_mutating_input(self):
		out = ProcessedPhotoData(photo_id='p1', detected_objects=INCOMING).detected_objects
		assert [o['blurred'] for o in out['objects']] == [True, True, False, True, False, True]
		assert out['objects'][0]['blurred_from'] == 'legacy-no-confidence'
		assert out['objects'][2]['blurred_from'] == 'legacy-confidence-0.4'
		assert 'blurred' not in LEGACY
		assert out['model_name'] == INCOMING['model_name']
		assert out['objects'][3:] == ALL_OBJECTS[3:]

	@pytest.mark.parametrize('detected', [None, {}, {'objects': []}, {'objects': [], 'manual': True}])
	def test_no_objects_are_invented(self, detected):
		assert ProcessedPhotoData(photo_id='p1', detected_objects=detected).detected_objects == detected

	@pytest.mark.parametrize('obj', [{'blurred': 'false'}, {'confidence': 'bad'}, None])
	def test_invalid_objects_are_rejected_before_storage(self, obj):
		with pytest.raises(ValueError):
			ProcessedPhotoData(photo_id='p1', detected_objects={'objects': [obj]})


class TestIsBlurred:
	"""Stored decisions are explicit; confidence is a writer concern."""

	@pytest.mark.parametrize('obj', [LEGACY, CONF_HIGH, CONF_LOW, {'confidence': BLUR_CONFIDENCE}])
	def test_stored_legacy_objects_are_rejected(self, obj):
		with pytest.raises(ValueError, match='explicit boolean'):
			is_blurred(obj)

	def test_confidence_threshold_is_still_used_for_new_writer_decisions(self):
		assert should_blur(CONF_HIGH) is True
		assert should_blur(CONF_LOW) is False
		assert should_blur({'confidence': BLUR_CONFIDENCE}) is True

	@pytest.mark.parametrize('flag', [False, True])
	def test_reading_a_flag_does_not_evaluate_confidence(self, flag):
		assert is_blurred({'blurred': flag, 'confidence': 'not evaluated'}) is flag

	@pytest.mark.parametrize('flag', [None, 'false', 0, 1, []])
	def test_non_boolean_stored_flags_are_rejected(self, flag):
		with pytest.raises(ValueError, match='explicit boolean'):
			is_blurred({'blurred': flag})

	def test_persisted_flag_wins_over_the_threshold(self):
		# A threshold move must not retroactively rewrite what was painted.
		assert is_blurred(FLAGGED_ON) is True
		assert is_blurred(FLAGGED_OFF) is False

	def test_manual_rectangle_is_blurred(self):
		assert is_blurred(MANUAL) is True


class TestBlurredOnly:

	def test_keeps_only_the_boxes_that_were_painted(self):
		assert blurred_only(DETECTED)['objects'] == BLURRED_OBJECTS

	def test_keeps_the_container_keys(self):
		# model_name/manual describe the pass, not its subjects.
		out = blurred_only({'objects': [ALL_OBJECTS[2]], 'model_name': 'yolo11x.pt', 'manual': False})
		assert out['model_name'] == 'yolo11x.pt'
		assert out['manual'] is False
		assert out['objects'] == []

	def test_does_not_mutate_the_input(self):
		blurred_only(DETECTED)
		assert DETECTED['objects'] == ALL_OBJECTS

	@pytest.mark.parametrize('value', [None, {}, {'objects': []}, {'objects': None}, []])
	def test_nothing_to_filter_passes_through(self, value):
		assert blurred_only(value) == value


def _db(detected_objects=DETECTED, is_public=True, owner_id=OWNER_ID):
	db = AsyncMock()
	result = Mock()
	result.first.return_value = (detected_objects, is_public, owner_id, 4000, 3000)
	db.execute.return_value = result
	return db


def _user(user_id, role=UserRole.USER):
	return Mock(id=user_id, role=role)


class TestDetectionsEndpointScope:

	@pytest.mark.asyncio
	async def test_public_read_does_not_guess_decisions_for_unmigrated_rows(self):
		with pytest.raises(ValueError, match='explicit boolean'):
			await get_photo_detections('p1', current_user=None, db=_db(INCOMING))

	@pytest.mark.asyncio
	async def test_anonymous_gets_only_the_blurred_boxes(self):
		out = await get_photo_detections('p1', current_user=None, db=_db())
		assert out['scope'] == 'blurred'
		assert out['detected_objects']['objects'] == BLURRED_OBJECTS

	@pytest.mark.asyncio
	async def test_other_signed_in_user_gets_only_the_blurred_boxes(self):
		out = await get_photo_detections('p1', current_user=_user('someone-else'), db=_db())
		assert out['scope'] == 'blurred'
		assert out['detected_objects']['objects'] == BLURRED_OBJECTS

	@pytest.mark.asyncio
	async def test_owner_gets_everything_recorded(self):
		out = await get_photo_detections('p1', current_user=_user(OWNER_ID), db=_db())
		assert out['scope'] == 'all'
		assert out['detected_objects']['objects'] == ALL_OBJECTS

	@pytest.mark.parametrize('role', [UserRole.ADMIN, UserRole.MODERATOR])
	@pytest.mark.asyncio
	async def test_moderator_gets_everything_recorded(self, role):
		out = await get_photo_detections('p1', current_user=_user('mod-1', role), db=_db())
		assert out['scope'] == 'all'
		assert out['detected_objects']['objects'] == ALL_OBJECTS

	@pytest.mark.asyncio
	async def test_moderator_sees_no_photo_they_could_not_see_before(self):
		# The wider scope is more of one photo, not more photos: a non-public
		# photo stays 404 for everyone but its owner.
		with pytest.raises(Exception) as exc:
			await get_photo_detections(
				'p1', current_user=_user('mod-1', UserRole.MODERATOR),
				db=_db(is_public=False))
		assert getattr(exc.value, 'status_code', None) == 404

	@pytest.mark.asyncio
	async def test_owner_of_a_private_photo_still_gets_it(self):
		out = await get_photo_detections('p1', current_user=_user(OWNER_ID), db=_db(is_public=False))
		assert out['scope'] == 'all'

	@pytest.mark.asyncio
	async def test_dimensions_ride_along_for_the_overlay_rescale(self):
		# The boxes are in original-resolution pixels; the web variant is
		# width-capped, so the client needs the detection space.
		out = await get_photo_detections('p1', current_user=None, db=_db())
		assert (out['width'], out['height']) == (4000, 3000)
