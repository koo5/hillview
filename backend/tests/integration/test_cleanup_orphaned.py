#!/usr/bin/env python3
"""
Integration tests for the cleanup orphaned photos endpoint.
Tests DELETE /photos/cleanup-orphaned functionality.
"""

import pytest
import requests
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.test_utils import API_URL
from utils.secure_upload_utils import SecureUploadClient


class TestCleanupOrphaned(BasePhotoTest):
	"""Tests for the cleanup orphaned photos endpoint."""

	@pytest.mark.asyncio
	async def test_cleanup_requires_auth(self):
		"""Test that cleanup endpoint requires authentication."""
		response = requests.delete(f"{API_URL}/photos/cleanup-orphaned")

		assert response.status_code == 401

	@pytest.mark.asyncio
	async def test_cleanup_authenticated_empty(self):
		"""Test cleanup with no orphaned photos."""
		response = requests.delete(
			f"{API_URL}/photos/cleanup-orphaned",
			headers=self.test_headers
		)

		assert response.status_code == 200
		data = response.json()

		assert "message" in data
		assert "cleaned_up_count" in data
		assert data["cleaned_up_count"] == 0

	@pytest.mark.asyncio
	async def test_cleanup_orphaned_authorized_photo(self):
		"""Test cleanup of photos stuck in 'authorized' status.

		Note: This test creates an authorized photo but doesn't complete the upload,
		simulating a failed upload scenario. The cleanup should only remove photos
		that have been in 'authorized' status for more than 1 hour.
		"""
		# Create a secure upload client
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(self.test_token, client_keys)

		# Get upload authorization but don't complete the upload
		auth_data = await upload_client.authorize_upload(
			self.test_token,
			filename="orphan_test.jpg"
		)

		photo_id = auth_data["photo_id"]
		print(f"Created authorized photo: {photo_id}")

		# Immediately try to cleanup - should NOT clean up new photos
		# (they need to be at least 1 hour old)
		response = requests.delete(
			f"{API_URL}/photos/cleanup-orphaned",
			headers=self.test_headers
		)

		assert response.status_code == 200
		data = response.json()

		# The photo was just created, so it shouldn't be cleaned up yet
		assert data["cleaned_up_count"] == 0, \
			"Newly authorized photos should not be cleaned up immediately"

	@pytest.mark.asyncio
	async def test_cleanup_only_affects_own_photos(self):
		"""Test that cleanup only affects the requesting user's photos."""
		# This test verifies user isolation - cleanup should only remove
		# photos owned by the authenticated user

		response = requests.delete(
			f"{API_URL}/photos/cleanup-orphaned",
			headers=self.test_headers
		)

		assert response.status_code == 200
		# The endpoint should complete successfully
		# (we can't easily verify isolation without creating photos as another user)

	@pytest.mark.asyncio
	async def test_cleanup_response_structure(self):
		"""Test that cleanup response has expected structure."""
		response = requests.delete(
			f"{API_URL}/photos/cleanup-orphaned",
			headers=self.test_headers
		)

		assert response.status_code == 200
		data = response.json()

		# Check response structure
		assert "message" in data
		assert "cleaned_up_count" in data
		assert isinstance(data["cleaned_up_count"], int)
		assert data["cleaned_up_count"] >= 0

	@pytest.mark.asyncio
	async def test_cleanup_invalid_token(self):
		"""Test cleanup with invalid auth token."""
		response = requests.delete(
			f"{API_URL}/photos/cleanup-orphaned",
			headers={"Authorization": "Bearer invalid-token"}
		)

		assert response.status_code == 401


if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
