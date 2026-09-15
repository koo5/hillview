#!/usr/bin/env python3
"""Integration tests for GET /api/bestof/lastmod — the sitemap's /bestof <lastmod>.

The endpoint fingerprints page 1 of the ranking on every call and moves its
timestamp only when the fingerprint differs from the stored one (site_state,
migration 035). So, against a cleared database:
  - an empty ranking still yields a lastmod (a fingerprint of nothing is a
    fingerprint), and repeated calls return the same value
  - a photo entering page 1 (its first annotation) moves it forward
  - a photo leaving page 1 (annotation deleted, score back to zero) moves it
    again — the case no input timestamp could have told us about
  - a change that leaves page 1 identical (a no-op re-title) does not move it

Asserts on global ranking state, hence clear_test_database() in setup_method
(see the same pattern in test_hillview_filtering.py).
"""

import pytest
import requests
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.test_utils import API_URL, clear_test_database, upload_test_image, wait_for_photo_processing
from utils.image_utils import create_test_image_full_gps


class TestBestofLastmod(BasePhotoTest):

	def setup_method(self, method=None):
		super().setup_method(method)
		clear_test_database()
		# The clear takes the test users with it; this recreates them.
		self.__class__.auth_helper.clear_token_cache()
		self.test_token, _ = self.get_different_user_tokens()
		self.test_headers = self.get_auth_headers(self.test_token)

	def _lastmod(self) -> str:
		response = requests.get(f"{API_URL}/bestof/lastmod")
		self.assert_success(response, "bestof lastmod should be public")
		value = response.json()["lastmod"]
		assert isinstance(value, str) and value.endswith("Z"), value
		return value

	async def _create_test_photo(self, filename: str) -> str:
		image_data = create_test_image_full_gps(200, 150, (0, 128, 255), lat=50.0755, lon=14.4378, bearing=90.0)
		photo_id = await upload_test_image(filename, image_data, "", self.test_token)
		wait_for_photo_processing(photo_id, self.test_token, timeout=30)
		return photo_id

	def _annotate(self, photo_id: str) -> str:
		response = requests.post(
			f"{API_URL}/annotations/photos/{photo_id}",
			json={"body": "A hill", "target": {"selector": {"type": "RECTANGLE", "geometry": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}}}},
			headers=self.test_headers,
		)
		assert response.status_code == 201, response.text
		return response.json()["id"]

	@pytest.mark.asyncio
	async def test_lastmod_moves_with_page_one_only(self):
		empty = self._lastmod()
		assert self._lastmod() == empty, "an unchanged (empty) ranking must not move"

		photo_id = await self._create_test_photo("bestof_lastmod.jpg")
		assert self._lastmod() == empty, "a zero-score upload is not in the ranking"

		annotation_id = self._annotate(photo_id)
		entered = self._lastmod()
		assert entered > empty, (entered, empty)
		assert self._lastmod() == entered

		# Same page, same fingerprint: a re-title that changes nothing.
		requests.patch(f"{API_URL}/photos/{photo_id}", json={"title": ""}, headers=self.test_headers)
		assert self._lastmod() == entered, "a no-op edit must not move it"

		# A real card-text change is a page change even though the order is not.
		response = requests.patch(f"{API_URL}/photos/{photo_id}", json={"title": "Named"}, headers=self.test_headers)
		self.assert_success(response, "owner retitle")
		retitled = self._lastmod()
		assert retitled > entered, (retitled, entered)

		response = requests.delete(f"{API_URL}/annotations/{annotation_id}", headers=self.test_headers)
		assert response.status_code == 204, response.text
		left = self._lastmod()
		assert left > retitled, (left, retitled)
		assert self._lastmod() == left
