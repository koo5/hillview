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

from common.detections import BLUR_CONFIDENCE, blurred_only, is_blurred  # noqa: E402
from common.models import UserRole  # noqa: E402
from photo_routes import get_photo_detections  # noqa: E402

OWNER_ID = 'owner-1'

# One object per stored format (see common/detections.py), split by verdict.
LEGACY = {'class_id': 0, 'class_name': 'person', 'blur': 151, 'bbox': {'x1': 0, 'y1': 0, 'x2': 9, 'y2': 9}}
CONF_HIGH = {'class_id': 2, 'class_name': 'car', 'confidence': 0.9, 'scale': 1.0, 'bbox': {'x1': 1, 'y1': 1, 'x2': 9, 'y2': 9}}
CONF_LOW = {'class_id': 0, 'class_name': 'person', 'confidence': 0.3, 'scale': 0.5, 'bbox': {'x1': 2, 'y1': 2, 'x2': 9, 'y2': 9}}
FLAGGED_ON = {'class_id': 7, 'class_name': 'truck', 'confidence': 0.8, 'blurred': True, 'bbox': {'x1': 3, 'y1': 3, 'x2': 9, 'y2': 9}}
FLAGGED_OFF = {'class_id': 0, 'class_name': 'person', 'confidence': 0.31, 'blurred': False, 'bbox': {'x1': 4, 'y1': 4, 'x2': 9, 'y2': 9}}
MANUAL = {'class_id': None, 'blur': 500, 'blurred': True, 'bbox': {'x1': 5, 'y1': 5, 'x2': 9, 'y2': 9}}

ALL_OBJECTS = [LEGACY, CONF_HIGH, CONF_LOW, FLAGGED_ON, FLAGGED_OFF, MANUAL]
BLURRED_OBJECTS = [LEGACY, CONF_HIGH, FLAGGED_ON, MANUAL]

DETECTED = {'objects': ALL_OBJECTS, 'model_name': 'yolo11x.pt'}


class TestIsBlurred:
	"""The four stored formats, each read the way its writer meant it."""

	def test_legacy_without_confidence_is_blurred(self):
		# Format #1 predates both the confidence and the flag: it was blurred
		# unconditionally when it was written.
		assert is_blurred(LEGACY) is True

	def test_confidence_is_compared_to_the_blur_threshold(self):
		assert is_blurred(CONF_HIGH) is True
		assert is_blurred(CONF_LOW) is False
		assert is_blurred({'confidence': BLUR_CONFIDENCE}) is True

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
		out = blurred_only({'objects': [CONF_LOW], 'model_name': 'yolo11x.pt', 'manual': False})
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
