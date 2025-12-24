#!/usr/bin/env python3
"""
Integration tests for the photo sharing endpoint.
Tests GET /photos/share/{photo_uid} functionality for social sharing metadata.
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


class TestPhotoSharing(BasePhotoTest):
	"""Tests for the photo sharing metadata endpoint."""

	@pytest.mark.asyncio
	async def test_share_hillview_photo(self):
		"""Test getting share metadata for a hillview photo."""
		# Upload a test photo
		image_data = create_test_image_full_gps(
			width=800, height=600, color=(200, 100, 50),
			lat=48.8566, lon=2.3522, bearing=270.0
		)

		photo_id = await upload_test_image(
			"share_test.jpg", image_data,
			"Photo for sharing test", self.test_token
		)

		photo_data = wait_for_photo_processing(photo_id, self.test_token, timeout=30)
		assert photo_data["processing_status"] == "completed"

		# Get share metadata (no auth required for social sharing)
		response = requests.get(f"{API_URL}/photos/share/hillview-{photo_id}")

		assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
		data = response.json()

		# Check required fields for social sharing
		assert "source" in data
		assert data["source"] == "hillview"
		assert "id" in data

	@pytest.mark.asyncio
	async def test_share_invalid_uid_format(self):
		"""Test that invalid photo UID format returns 400."""
		response = requests.get(f"{API_URL}/photos/share/invalid-format-without-source")

		# The endpoint expects {source}-{id} format
		# "invalid-format-without-source" has dashes but first part isn't a valid source
		# Let's test with completely invalid format
		response = requests.get(f"{API_URL}/photos/share/nohyphen")
		assert response.status_code == 400

	@pytest.mark.asyncio
	async def test_share_nonexistent_photo(self):
		"""Test that nonexistent photo returns 404."""
		response = requests.get(f"{API_URL}/photos/share/hillview-nonexistent-id-12345")

		assert response.status_code == 404

	@pytest.mark.asyncio
	async def test_share_no_auth_required(self):
		"""Test that share endpoint works without authentication."""
		# Upload a photo first (with auth)
		image_data = create_test_image_full_gps(
			width=400, height=300, color=(100, 200, 100),
			lat=40.7128, lon=-74.0060, bearing=90.0
		)

		photo_id = await upload_test_image(
			"public_share.jpg", image_data,
			"Public sharing test", self.test_token
		)

		wait_for_photo_processing(photo_id, self.test_token, timeout=30)

		# Access share endpoint without authentication
		response = requests.get(
			f"{API_URL}/photos/share/hillview-{photo_id}"
			# No headers - unauthenticated request
		)

		assert response.status_code == 200, "Share endpoint should work without auth"

	@pytest.mark.asyncio
	async def test_share_mapillary_photo_format(self):
		"""Test share endpoint with mapillary source format."""
		# Mapillary photos use numeric IDs
		# This should return 404 since we don't have that photo, but format is valid
		response = requests.get(f"{API_URL}/photos/share/mapillary-123456789")

		# Either 404 (not found) or 200 if somehow exists
		assert response.status_code in [200, 404]

	@pytest.mark.asyncio
	async def test_share_response_structure(self):
		"""Test that share response has proper structure for social sharing."""
		# Upload a photo
		image_data = create_test_image_full_gps(
			width=1024, height=768, color=(150, 150, 200),
			lat=35.6762, lon=139.6503, bearing=45.0
		)

		photo_id = await upload_test_image(
			"structure_share.jpg", image_data,
			"Structure test for sharing", self.test_token
		)

		wait_for_photo_processing(photo_id, self.test_token, timeout=30)

		response = requests.get(f"{API_URL}/photos/share/hillview-{photo_id}")
		assert response.status_code == 200

		data = response.json()

		# Social sharing typically needs these fields
		expected_fields = ["source", "id"]
		for field in expected_fields:
			assert field in data, f"Missing expected field for social sharing: {field}"


class TestPhotoSharingEdgeCases(BasePhotoTest):
	"""Edge case tests for photo sharing."""

	@pytest.mark.asyncio
	async def test_share_empty_source(self):
		"""Test share with empty source."""
		response = requests.get(f"{API_URL}/photos/share/-12345")
		# Should be invalid format
		assert response.status_code in [400, 404]

	@pytest.mark.asyncio
	async def test_share_empty_id(self):
		"""Test share with empty id."""
		response = requests.get(f"{API_URL}/photos/share/hillview-")
		assert response.status_code in [400, 404]

	@pytest.mark.asyncio
	async def test_share_special_characters_in_id(self):
		"""Test share with special characters in ID."""
		response = requests.get(f"{API_URL}/photos/share/hillview-../../../etc/passwd")
		# Should be rejected - either 400 or 404
		assert response.status_code in [400, 404, 422]


if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
