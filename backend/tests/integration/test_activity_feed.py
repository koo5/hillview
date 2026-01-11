#!/usr/bin/env python3
"""
Integration tests for the activity feed endpoint.
Tests GET /activity/recent functionality.
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


class TestActivityFeed(BasePhotoTest):
	"""Tests for the activity feed endpoint."""

	@pytest.mark.asyncio
	async def test_activity_feed_unauthenticated(self):
		"""Test that activity feed works without authentication."""
		response = requests.get(f"{API_URL}/activity/recent")

		assert response.status_code == 200, f"Expected 200, got {response.status_code}"
		data = response.json()

		assert "photos" in data
		assert "has_more" in data
		assert "next_cursor" in data
		assert isinstance(data["photos"], list)

	@pytest.mark.asyncio
	async def test_activity_feed_authenticated(self):
		"""Test that activity feed works with authentication."""
		response = requests.get(
			f"{API_URL}/activity/recent",
			headers=self.test_headers
		)

		assert response.status_code == 200
		data = response.json()

		assert "photos" in data
		assert isinstance(data["photos"], list)

	@pytest.mark.asyncio
	async def test_activity_feed_with_photos(self):
		"""Test activity feed returns uploaded photos."""
		# Upload a test photo
		image_data = create_test_image_full_gps(
			width=200, height=150, color=(100, 150, 200),
			lat=50.0755, lon=14.4378, bearing=45.0
		)

		photo_id = await upload_test_image(
			"activity_test.jpg", image_data,
			"Activity feed test photo", self.test_token
		)

		# Wait for processing
		photo_data = wait_for_photo_processing(photo_id, self.test_token, timeout=30)
		assert photo_data["processing_status"] == "completed"

		# Check activity feed
		response = requests.get(
			f"{API_URL}/activity/recent",
			headers=self.test_headers
		)

		assert response.status_code == 200
		data = response.json()

		# Our photo should be in the feed
		photo_ids = [p["id"] for p in data["photos"]]
		assert photo_id in photo_ids, f"Uploaded photo {photo_id} not found in activity feed"

		# Check photo structure
		our_photo = next(p for p in data["photos"] if p["id"] == photo_id)
		assert "owner_username" in our_photo
		assert "uploaded_at" in our_photo
		assert "latitude" in our_photo
		assert "longitude" in our_photo

	@pytest.mark.asyncio
	async def test_activity_feed_limit_parameter(self):
		"""Test that limit parameter works correctly."""
		response = requests.get(
			f"{API_URL}/activity/recent?limit=5",
			headers=self.test_headers
		)

		assert response.status_code == 200
		data = response.json()

		assert len(data["photos"]) <= 5

	@pytest.mark.asyncio
	async def test_activity_feed_pagination(self):
		"""Test cursor-based pagination."""
		# Get first page
		response1 = requests.get(
			f"{API_URL}/activity/recent?limit=2",
			headers=self.test_headers
		)

		assert response1.status_code == 200
		data1 = response1.json()

		if data1["has_more"] and data1["next_cursor"]:
			# Get second page using cursor
			response2 = requests.get(
				f"{API_URL}/activity/recent?limit=2&cursor={data1['next_cursor']}",
				headers=self.test_headers
			)

			assert response2.status_code == 200
			data2 = response2.json()

			# Pages should have different photos
			ids1 = set(p["id"] for p in data1["photos"])
			ids2 = set(p["id"] for p in data2["photos"])
			assert ids1.isdisjoint(ids2), "Pagination returned duplicate photos"

	@pytest.mark.asyncio
	async def test_activity_feed_invalid_cursor(self):
		"""Test that invalid cursor returns 400 error."""
		response = requests.get(
			f"{API_URL}/activity/recent?cursor=invalid-cursor-format",
			headers=self.test_headers
		)

		assert response.status_code == 400
		assert "cursor" in response.json().get("detail", "").lower()

	@pytest.mark.asyncio
	async def test_activity_feed_photo_structure(self):
		"""Test that activity feed photos have required fields."""
		# Upload a photo first
		image_data = create_test_image_full_gps(
			width=200, height=150, color=(50, 100, 150),
			lat=51.5074, lon=-0.1278, bearing=180.0
		)

		photo_id = await upload_test_image(
			"structure_test.jpg", image_data,
			"Structure test photo", self.test_token
		)

		wait_for_photo_processing(photo_id, self.test_token, timeout=30)

		response = requests.get(f"{API_URL}/activity/recent")
		assert response.status_code == 200

		data = response.json()
		if data["photos"]:
			photo = data["photos"][0]

			# Check required fields
			required_fields = [
				"id", "original_filename", "uploaded_at",
				"processing_status", "owner_username", "owner_id"
			]
			for field in required_fields:
				assert field in photo, f"Missing required field: {field}"


if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
