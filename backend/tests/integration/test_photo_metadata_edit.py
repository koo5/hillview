#!/usr/bin/env python3
"""Integration tests for photo metadata editing.

Covers PATCH /api/photos/{photo_id} — the partial edit of a photo's title,
description, bearing and featured flag behind the edit form on the /photo/{uid}
detail page.

The interesting behaviours, all asserted below:
  - authorization: owners edit their own photo, moderators edit any, other
    regular users get 404 (existence hidden, as for DELETE)
  - `featured` is a curation flag: only moderators may CHANGE it (403), though
    an owner re-submitting the current value is a harmless no-op
  - partial semantics: omitted fields unchanged, empty string CLEARS a field
  - bearing is normalized into [0, 360)
  - non-owner edits write a moderation-audit row (action='edit') carrying the
    old/new values, while owner self-edits write nothing
"""

import pytest
import requests
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.test_utils import API_URL, upload_test_image, wait_for_photo_processing
from utils.image_utils import create_test_image_full_gps


class TestPhotoMetadataEdit(BasePhotoTest):
	"""Tests for PATCH /api/photos/{photo_id} (photo metadata edit)."""

	def setUp(self):
		super().setUp()
		self.uploaded_photo_ids = []

	def tearDown(self):
		for photo_id in self.uploaded_photo_ids:
			try:
				requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
			except Exception:
				pass
		super().tearDown()

	async def _create_test_photo(self, filename: str, description: str = "Moderation edit fixture",
	                             token: str = None) -> str:
		"""Upload a processed test photo (owned by `test` unless a token is given)."""
		image_data = create_test_image_full_gps(200, 150, (0, 128, 255), lat=50.0755, lon=14.4378, bearing=90.0)
		photo_id = await upload_test_image(filename, image_data, description, token or self.test_token)
		self.uploaded_photo_ids.append(photo_id)
		wait_for_photo_processing(photo_id, token or self.test_token, timeout=30)
		return photo_id

	def _moderator_headers(self):
		return self.get_auth_headers(self.get_test_token("moderator"))

	def _public_photo(self, photo_id: str) -> dict:
		"""The photo as the detail page sees it (this is what the form reads back)."""
		response = requests.get(f"{API_URL}/photos/public/hillview-{photo_id}")
		self.assert_success(response, "Public photo should be readable")
		return response.json()

	def _audit_entries_for(self, photo_id: str) -> list:
		response = requests.get(
			f"{API_URL}/photos/moderation-audit",
			params={"limit": 200},
			headers=self.get_auth_headers(self.get_admin_token()),
		)
		self.assert_success(response, "Should be able to read moderation audit")
		return [e for e in response.json()["entries"] if e["photo_id"] == photo_id]

	@pytest.mark.asyncio
	async def test_moderator_edit_others_photo_with_audit(self):
		"""A moderator can edit another user's photo; the change lands in the audit."""
		photo_id = await self._create_test_photo("mod_edit_full.jpg")

		reason = "integration test: tidying metadata"
		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={
				"title": "Curated title",
				"description": "Curated description",
				"featured": True,
				"bearing": 123.5,
				"reason": reason,
			},
			headers=self._moderator_headers(),
		)
		self.assert_success(response, "Moderator should be able to edit another user's photo")
		body = response.json()
		assert body["title"] == "Curated title", body
		assert body["description"] == "Curated description", body
		assert body["featured"] is True, body
		assert body["bearing"] == 123.5, body
		assert sorted(body["changed"]) == ["bearing", "description", "featured", "title"], body

		# Persisted, and visible on the endpoint the detail page reads.
		public = self._public_photo(photo_id)
		assert public["title"] == "Curated title", public
		assert public["description"] == "Curated description", public
		assert public["featured"] is True, public
		assert public["bearing"] == 123.5, public

		# Exactly one audit entry, with the old/new values snapshotted.
		entries = self._audit_entries_for(photo_id)
		assert len(entries) == 1, f"Expected exactly one audit entry, got {len(entries)}"
		entry = entries[0]
		assert entry["action"] == "edit", entry
		assert entry["actor_username"] == "moderator", entry
		assert entry["actor_role"] == "moderator", entry
		assert entry["photo_owner_username"] == "test", entry
		assert entry["reason"] == reason, entry

		changes = entry["extra_data"]["changes"]
		assert changes["title"]["new"] == "Curated title", changes
		assert changes["featured"] == {"old": False, "new": True}, changes
		assert changes["bearing"]["old"] == 90.0, changes
		assert changes["bearing"]["new"] == 123.5, changes

	@pytest.mark.asyncio
	async def test_owner_can_edit_own_metadata(self):
		"""An ordinary owner may retitle/redescribe/re-aim their own photo."""
		photo_id = await self._create_test_photo("owner_edit.jpg", "Original description")

		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={
				"title": "My own title",
				"description": "My own description",
				"bearing": 12.5,
			},
			headers=self.test_headers,
		)
		self.assert_success(response, "Owner should be able to edit their own photo")
		assert sorted(response.json()["changed"]) == ["bearing", "description", "title"], response.json()

		public = self._public_photo(photo_id)
		assert public["title"] == "My own title", public
		assert public["description"] == "My own description", public
		assert public["bearing"] == 12.5, public

		assert self._audit_entries_for(photo_id) == [], "Owner self-edit must not be audited"

	@pytest.mark.asyncio
	async def test_owner_cannot_change_featured(self):
		"""`featured` is a curation flag — an owner must not be able to self-promote."""
		photo_id = await self._create_test_photo("owner_edit_featured.jpg")

		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"title": "Should not stick", "featured": True},
			headers=self.test_headers,
		)
		self.assert_forbidden(response, "Owner must not be able to set featured")

		# The whole edit is rejected, so the title must not have landed either.
		public = self._public_photo(photo_id)
		assert public["title"] != "Should not stick", public
		assert public["featured"] is False, public
		assert self._audit_entries_for(photo_id) == [], "A denied edit must not be audited"

	@pytest.mark.asyncio
	async def test_owner_may_resubmit_unchanged_featured(self):
		"""Sending featured at its current value is a no-op, so a full-form save works."""
		photo_id = await self._create_test_photo("owner_edit_featured_noop.jpg")

		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"title": "Full form save", "featured": False},
			headers=self.test_headers,
		)
		self.assert_success(response, "Re-submitting the current featured value must be allowed")
		assert response.json()["changed"] == ["title"], response.json()
		assert self._public_photo(photo_id)["title"] == "Full form save"

	@pytest.mark.asyncio
	async def test_other_regular_user_gets_404(self):
		"""A regular user who doesn't own the photo can't edit it, and isn't told it exists."""
		photo_id = await self._create_test_photo("other_user_edit.jpg", "Original description")

		other_headers = self.get_auth_headers(self.get_test_token("testuser"))
		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"title": "Not my photo"},
			headers=other_headers,
		)
		assert response.status_code == 404, f"Non-owner regular user should get 404, got {response.status_code}"

		assert self._public_photo(photo_id)["title"] != "Not my photo"
		assert self._audit_entries_for(photo_id) == [], "A denied edit must not be audited"

	@pytest.mark.asyncio
	async def test_unauthenticated_rejected(self):
		"""An unauthenticated edit is rejected outright."""
		photo_id = await self._create_test_photo("mod_edit_unauth.jpg")

		response = requests.patch(f"{API_URL}/photos/{photo_id}", json={"featured": True})
		self.assert_unauthorized(response, "Unauthenticated edit should be rejected")

		assert self._public_photo(photo_id)["featured"] is False

	@pytest.mark.asyncio
	async def test_partial_edit_leaves_other_fields_untouched(self):
		"""Fields omitted from the payload are left alone."""
		photo_id = await self._create_test_photo("mod_edit_partial.jpg", "Keep this description")

		before = self._public_photo(photo_id)
		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"title": "Only the title changes"},
			headers=self._moderator_headers(),
		)
		self.assert_success(response)
		assert response.json()["changed"] == ["title"], response.json()

		after = self._public_photo(photo_id)
		assert after["title"] == "Only the title changes", after
		assert after["description"] == before["description"], after
		assert after["featured"] == before["featured"], after
		assert after["bearing"] == before["bearing"], after

	@pytest.mark.asyncio
	async def test_empty_string_clears_field(self):
		"""An empty/whitespace title clears it — moderators must be able to strip text."""
		photo_id = await self._create_test_photo("mod_edit_clear.jpg")

		requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"title": "Offensive title"},
			headers=self._moderator_headers(),
		)
		assert self._public_photo(photo_id)["title"] == "Offensive title"

		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"title": "   "},
			headers=self._moderator_headers(),
		)
		self.assert_success(response)
		assert response.json()["title"] is None, response.json()
		assert self._public_photo(photo_id)["title"] is None

	@pytest.mark.asyncio
	async def test_bearing_normalized_into_range(self):
		"""Out-of-range bearings wrap into [0, 360) rather than being stored raw."""
		photo_id = await self._create_test_photo("mod_edit_bearing.jpg")

		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"bearing": 450},
			headers=self._moderator_headers(),
		)
		self.assert_success(response)
		assert response.json()["bearing"] == 90.0, response.json()

		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"bearing": -90},
			headers=self._moderator_headers(),
		)
		self.assert_success(response)
		assert response.json()["bearing"] == 270.0, response.json()
		assert self._public_photo(photo_id)["bearing"] == 270.0

	@pytest.mark.asyncio
	async def test_noop_edit_creates_no_audit(self):
		"""Re-submitting the current values reports no change and writes no audit row."""
		photo_id = await self._create_test_photo("mod_edit_noop.jpg", "Unchanged description")

		current = self._public_photo(photo_id)
		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={
				"title": current["title"] or "",
				"description": current["description"] or "",
				"featured": current["featured"],
				"bearing": current["bearing"],
			},
			headers=self._moderator_headers(),
		)
		self.assert_success(response)
		assert response.json()["changed"] == [], response.json()
		assert self._audit_entries_for(photo_id) == [], "A no-op edit must not be audited"

	@pytest.mark.asyncio
	async def test_owner_self_edit_creates_no_audit(self):
		"""An admin editing their OWN photo is not a moderation action — no audit row."""
		admin_token = self.get_admin_token()
		photo_id = await self._create_test_photo("mod_edit_own.jpg", token=admin_token)

		response = requests.patch(
			f"{API_URL}/photos/{photo_id}",
			json={"title": "My own photo", "featured": True},
			headers=self.get_auth_headers(admin_token),
		)
		self.assert_success(response, "Admin should be able to edit their own photo")
		assert sorted(response.json()["changed"]) == ["featured", "title"], response.json()

		assert self._audit_entries_for(photo_id) == [], "Self-edit must not be recorded in the audit"

		# Owned by admin, so the test-user teardown can't clean it up.
		requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.get_auth_headers(admin_token))
		self.uploaded_photo_ids.remove(photo_id)

	def test_edit_nonexistent_photo(self):
		"""Editing a photo that doesn't exist is a 404, even for a moderator."""
		response = requests.patch(
			f"{API_URL}/photos/nonexistent-photo-id",
			json={"featured": True},
			headers=self._moderator_headers(),
		)
		assert response.status_code == 404, f"Should be 404, got {response.status_code}"


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
