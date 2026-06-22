#!/usr/bin/env python3
"""
Integration tests for the capture-time timeline endpoint.
Tests GET /hillview/timeline (walk a user's photos by capture time).

These exercise the real upload pipeline, so each test uploads photos with
explicit, distinct captured_at values (10-minute gaps) and asserts the endpoint
returns them keyset-ordered by (captured_at, id) around an anchor.
"""

import pytest
import requests
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest
from utils.test_utils import API_URL, upload_test_image, wait_for_photo_processing
from utils.image_utils import create_test_image_full_gps
from utils.secure_upload_utils import generate_test_captured_at, SecureUploadClient


class TestPhotoTimeline(BaseUserManagementTest):
	"""Tests for the GET /hillview/timeline endpoint."""

	def _user_id(self, headers) -> str:
		"""Resolve a user's id from their auth headers."""
		r = requests.get(f"{API_URL}/user/profile", headers=headers)
		assert r.status_code == 200, f"profile lookup failed: {r.status_code} - {r.text}"
		return r.json()["id"]

	async def _upload(self, token: str, i: int, minutes_ago: int, is_public: bool = True) -> str:
		"""Upload one processed photo with a controlled capture time.

		`minutes_ago` sets captured_at (larger = older). `i` varies the image
		content/coords so each upload has a distinct MD5 (avoids dedup).
		"""
		image_data = create_test_image_full_gps(
			width=200, height=150,
			color=(40 + i * 30, 90, 150),
			lat=50.0755, lon=14.4378 + i * 0.001,
			bearing=(20 + i * 15) % 360
		)
		photo_id = await upload_test_image(
			f"tl_{i}.jpg", image_data, f"timeline test {i}", token,
			is_public=is_public,
			captured_at=generate_test_captured_at(minutes_ago=minutes_ago)
		)
		photo_data = wait_for_photo_processing(photo_id, token, timeout=30)
		assert photo_data["processing_status"] == "completed", \
			f"photo {photo_id} did not process: {photo_data.get('error')}"
		return photo_id

	async def _upload_no_capture_time(self, token: str, i: int) -> str:
		"""Upload a processed photo with NO capture time: omit captured_at at
		authorize; the generated image carries no EXIF datetime, so it stays null
		and effective_at falls back to upload time."""
		image_data = create_test_image_full_gps(
			width=200, height=150,
			color=(200, 80 + i, 60),
			lat=50.0755, lon=14.4378 + i * 0.001,
			bearing=(20 + i * 15) % 360
		)
		client = SecureUploadClient(api_url=API_URL)
		keys = client.generate_client_keys()
		await client.register_client_key(token, keys)
		auth = await client.authorize_upload_with_params(
			token, f"tl_nc_{i}.jpg", len(image_data),
			50.0755, 14.4378 + i * 0.001, "no capture time", True,
			file_data=image_data  # note: no captured_at passed
		)
		await client.upload_to_worker(image_data, auth, keys, f"tl_nc_{i}.jpg")
		photo_id = auth["photo_id"]
		photo_data = wait_for_photo_processing(photo_id, token, timeout=30)
		assert photo_data["processing_status"] == "completed", \
			f"photo {photo_id} did not process: {photo_data.get('error')}"
		return photo_id

	@pytest.mark.asyncio
	async def test_timeline_orders_by_capture_time(self):
		"""Returns all photos ascending by capture time, anchor in the middle."""
		test_id = self._user_id(self.test_headers)
		# Oldest first -> ids[] is already in ascending capture-time order.
		ids = [await self._upload(self.test_token, i, mins)
			   for i, mins in enumerate([50, 40, 30, 20, 10])]
		anchor = ids[2]

		r = requests.get(f"{API_URL}/hillview/timeline", params={
			"user_ids": test_id, "anchor_id": anchor, "before": 10, "after": 10
		}, headers=self.test_headers)
		assert r.status_code == 200, f"{r.status_code} - {r.text}"
		data = r.json()

		assert {"photos", "anchor_index", "has_more_before", "has_more_after"} <= set(data)
		returned = [p["id"] for p in data["photos"]]
		assert returned == ids, f"expected ascending {ids}, got {returned}"
		assert data["photos"][data["anchor_index"]]["id"] == anchor
		assert data["has_more_before"] is False
		assert data["has_more_after"] is False

		# Lightweight index shape (id/coords/bearing/captured_at/owner), not a full feed.
		p = data["photos"][0]
		assert "lat" in p and "lng" in p
		assert "bearing" in p and "captured_at" in p
		assert "uploaded_at" in p and "owner_id" in p

	@pytest.mark.asyncio
	async def test_timeline_before_after_window_and_has_more(self):
		"""before/after bound the window; has_more flags report photos beyond it."""
		test_id = self._user_id(self.test_headers)
		ids = [await self._upload(self.test_token, i, mins)
			   for i, mins in enumerate([50, 40, 30, 20, 10])]
		anchor = ids[2]

		r = requests.get(f"{API_URL}/hillview/timeline", params={
			"user_ids": test_id, "anchor_id": anchor, "before": 1, "after": 1
		}, headers=self.test_headers)
		assert r.status_code == 200, f"{r.status_code} - {r.text}"
		data = r.json()

		returned = [p["id"] for p in data["photos"]]
		assert returned == [ids[1], ids[2], ids[3]], f"got {returned}"
		assert data["anchor_index"] == 1
		assert data["photos"][1]["id"] == anchor
		assert data["has_more_before"] is True
		assert data["has_more_after"] is True

	@pytest.mark.asyncio
	async def test_timeline_scopes_to_requested_owner(self):
		"""A single-owner timeline excludes other users' photos."""
		test_id = self._user_id(self.test_headers)
		t0 = await self._upload(self.test_token, 0, 40)
		a1 = await self._upload(self.admin_token, 1, 30)  # admin photo, time-between
		t2 = await self._upload(self.test_token, 2, 20)

		r = requests.get(f"{API_URL}/hillview/timeline", params={
			"user_ids": test_id, "anchor_id": t0, "before": 10, "after": 10
		}, headers=self.test_headers)
		assert r.status_code == 200, f"{r.status_code} - {r.text}"
		ids = [p["id"] for p in r.json()["photos"]]
		assert t0 in ids and t2 in ids
		assert a1 not in ids, "another user's photo leaked into a single-owner timeline"

	@pytest.mark.asyncio
	async def test_timeline_merges_multiple_owners(self):
		"""Multiple owner ids merge into one timeline, still time-ordered."""
		test_id = self._user_id(self.test_headers)
		admin_id = self._user_id(self.admin_headers)
		t0 = await self._upload(self.test_token, 0, 40)
		a1 = await self._upload(self.admin_token, 1, 30)
		t2 = await self._upload(self.test_token, 2, 20)
		a3 = await self._upload(self.admin_token, 3, 10)

		r = requests.get(f"{API_URL}/hillview/timeline", params={
			"user_ids": f"{test_id},{admin_id}", "anchor_id": t0, "before": 10, "after": 10
		}, headers=self.test_headers)
		assert r.status_code == 200, f"{r.status_code} - {r.text}"
		ids = [p["id"] for p in r.json()["photos"]]
		assert ids == [t0, a1, t2, a3], f"merged timeline mis-ordered: {ids}"

	@pytest.mark.asyncio
	async def test_timeline_private_photo_visibility(self):
		"""Owner sees their own private photo; anonymous callers do not."""
		test_id = self._user_id(self.test_headers)
		t0 = await self._upload(self.test_token, 0, 40, is_public=True)
		tp = await self._upload(self.test_token, 1, 30, is_public=False)  # private, owned by test
		t2 = await self._upload(self.test_token, 2, 20, is_public=True)
		params = {"user_ids": test_id, "anchor_id": t0, "before": 10, "after": 10}

		r_owner = requests.get(f"{API_URL}/hillview/timeline", params=params, headers=self.test_headers)
		assert r_owner.status_code == 200, f"{r_owner.status_code} - {r_owner.text}"
		owner_ids = [p["id"] for p in r_owner.json()["photos"]]
		assert tp in owner_ids, "owner should see their own private photo on the timeline"

		r_anon = requests.get(f"{API_URL}/hillview/timeline", params=params)  # no auth
		assert r_anon.status_code == 200, f"{r_anon.status_code} - {r_anon.text}"
		anon_ids = [p["id"] for p in r_anon.json()["photos"]]
		assert tp not in anon_ids, "anonymous caller must not see a private photo"
		assert t0 in anon_ids and t2 in anon_ids, "public photos should still be visible anonymously"

	@pytest.mark.asyncio
	async def test_timeline_anchor_not_found(self):
		"""An unknown anchor id returns 404."""
		test_id = self._user_id(self.test_headers)
		r = requests.get(f"{API_URL}/hillview/timeline", params={
			"user_ids": test_id, "anchor_id": "does-not-exist", "before": 5, "after": 5
		}, headers=self.test_headers)
		assert r.status_code == 404, f"{r.status_code} - {r.text}"

	@pytest.mark.asyncio
	async def test_timeline_requires_user_ids(self):
		"""Empty user_ids is a bad request."""
		pid = await self._upload(self.test_token, 0, 10)
		r = requests.get(f"{API_URL}/hillview/timeline", params={
			"user_ids": "", "anchor_id": pid, "before": 5, "after": 5
		}, headers=self.test_headers)
		assert r.status_code == 400, f"{r.status_code} - {r.text}"

	@pytest.mark.asyncio
	async def test_timeline_falls_back_to_upload_time(self):
		"""A photo with no capture time still appears, ordered by upload time."""
		test_id = self._user_id(self.test_headers)
		old1 = await self._upload(self.test_token, 0, 50)              # captured 50 min ago
		old2 = await self._upload(self.test_token, 1, 40)              # captured 40 min ago
		nocap = await self._upload_no_capture_time(self.test_token, 2)  # no capture time → upload time (now)

		r = requests.get(f"{API_URL}/hillview/timeline", params={
			"user_ids": test_id, "anchor_id": old1, "before": 10, "after": 10
		}, headers=self.test_headers)
		assert r.status_code == 200, f"{r.status_code} - {r.text}"
		data = r.json()

		ids = [p["id"] for p in data["photos"]]
		assert nocap in ids, "no-capture-time photo should still appear (falls back to upload time)"
		# Uploaded last, so effective_at = upload time sorts it after the captured ones.
		assert ids.index(nocap) > ids.index(old2), "no-capture photo should sort by its recent upload time"
		# The endpoint still exposes the real (null) capture time + the upload fallback.
		entry = next(p for p in data["photos"] if p["id"] == nocap)
		assert entry["captured_at"] is None
		assert entry["uploaded_at"] is not None


if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
