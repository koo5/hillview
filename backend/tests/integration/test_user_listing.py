#!/usr/bin/env python3
"""
Integration tests for user listing endpoints.
Tests GET /users/ and GET /users/{user_id}/photos functionality.
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


class TestUserListing(BasePhotoTest):
	"""Tests for the user listing endpoint."""

	@pytest.mark.asyncio
	async def test_list_users_unauthenticated(self):
		"""Test that user listing works without authentication."""
		response = requests.get(f"{API_URL}/users/")

		assert response.status_code == 200
		data = response.json()

		# API returns a plain list of users
		assert isinstance(data, list)

	@pytest.mark.asyncio
	async def test_list_users_authenticated(self):
		"""Test user listing with authentication."""
		response = requests.get(
			f"{API_URL}/users/",
			headers=self.test_headers
		)

		assert response.status_code == 200
		data = response.json()

		assert isinstance(data, list)

	@pytest.mark.asyncio
	async def test_list_users_contains_test_user(self):
		"""Test that user listing includes our test user."""
		response = requests.get(f"{API_URL}/users/")

		assert response.status_code == 200
		data = response.json()

		# Find our test user
		usernames = [u.get("username") for u in data]
		assert "test" in usernames, "Test user should be in user listing"

	@pytest.mark.asyncio
	async def test_list_users_structure(self):
		"""Test that user listing has expected structure."""
		response = requests.get(f"{API_URL}/users/")

		assert response.status_code == 200
		data = response.json()

		if data:
			user = data[0]
			# Check for expected fields
			assert "id" in user
			assert "username" in user
			# Should NOT expose sensitive fields
			assert "password" not in user
			assert "hashed_password" not in user

	@pytest.mark.asyncio
	async def test_list_users_returns_all(self):
		"""Test that user listing returns all users (no pagination on this endpoint)."""
		response = requests.get(f"{API_URL}/users/")

		assert response.status_code == 200
		data = response.json()

		# Should have at least the test users we created
		assert len(data) >= 3


class TestUserPhotos(BasePhotoTest):
	"""Tests for the user photos endpoint."""

	@pytest.mark.asyncio
	async def test_get_user_photos_by_id(self):
		"""Test getting photos for a specific user."""
		# First, get user ID from profile
		profile_response = requests.get(
			f"{API_URL}/user/profile",
			headers=self.test_headers
		)
		assert profile_response.status_code == 200
		user_id = profile_response.json()["id"]

		# Upload a photo
		image_data = create_test_image_full_gps(
			width=200, height=150, color=(100, 100, 200),
			lat=52.5200, lon=13.4050, bearing=120.0
		)

		photo_id = await upload_test_image(
			"user_photos_test.jpg", image_data,
			"User photos test", self.test_token
		)

		wait_for_photo_processing(photo_id, self.test_token, timeout=30)

		# Get user's photos
		response = requests.get(f"{API_URL}/users/{user_id}/photos")

		assert response.status_code == 200
		data = response.json()

		assert "photos" in data
		assert isinstance(data["photos"], list)

		# Our photo should be in the list
		photo_ids = [p["id"] for p in data["photos"]]
		assert photo_id in photo_ids

	@pytest.mark.asyncio
	async def test_get_user_photos_nonexistent_user(self):
		"""Test getting photos for a nonexistent user."""
		response = requests.get(f"{API_URL}/users/nonexistent-user-id-12345/photos")

		assert response.status_code == 404

	@pytest.mark.asyncio
	async def test_get_user_photos_no_auth_required(self):
		"""Test that user photos endpoint works without authentication."""
		# Get user ID
		profile_response = requests.get(
			f"{API_URL}/user/profile",
			headers=self.test_headers
		)
		user_id = profile_response.json()["id"]

		# Access without auth
		response = requests.get(f"{API_URL}/users/{user_id}/photos")

		assert response.status_code == 200

	@pytest.mark.asyncio
	async def test_get_user_photos_pagination(self):
		"""Test user photos pagination."""
		# Get user ID
		profile_response = requests.get(
			f"{API_URL}/user/profile",
			headers=self.test_headers
		)
		user_id = profile_response.json()["id"]

		# Test with limit
		response = requests.get(f"{API_URL}/users/{user_id}/photos?limit=5")

		assert response.status_code == 200
		data = response.json()

		assert "photos" in data
		assert len(data["photos"]) <= 5
		# Pagination info is nested under "pagination"
		assert "pagination" in data
		assert "has_more" in data["pagination"]
		assert "next_cursor" in data["pagination"]

	@pytest.mark.asyncio
	async def test_get_user_photos_cursor_pagination(self):
		"""Test user photos cursor-based pagination."""
		# Get user ID
		profile_response = requests.get(
			f"{API_URL}/user/profile",
			headers=self.test_headers
		)
		user_id = profile_response.json()["id"]

		# First page
		response1 = requests.get(f"{API_URL}/users/{user_id}/photos?limit=2")
		assert response1.status_code == 200
		data1 = response1.json()

		pagination = data1.get("pagination", {})
		if pagination.get("has_more") and pagination.get("next_cursor"):
			# Second page
			response2 = requests.get(
				f"{API_URL}/users/{user_id}/photos?limit=2&cursor={pagination['next_cursor']}"
			)
			assert response2.status_code == 200
			data2 = response2.json()

			# Should have different photos
			ids1 = set(p["id"] for p in data1["photos"])
			ids2 = set(p["id"] for p in data2["photos"])
			assert ids1.isdisjoint(ids2), "Pagination should not return duplicates"

	@pytest.mark.asyncio
	async def test_get_user_photos_structure(self):
		"""Test user photos response structure."""
		# Get user ID
		profile_response = requests.get(
			f"{API_URL}/user/profile",
			headers=self.test_headers
		)
		user_id = profile_response.json()["id"]

		# Upload a photo to ensure we have data
		image_data = create_test_image_full_gps(
			width=300, height=200, color=(150, 100, 50),
			lat=41.9028, lon=12.4964, bearing=180.0
		)

		photo_id = await upload_test_image(
			"structure_test.jpg", image_data,
			"Structure test", self.test_token
		)

		wait_for_photo_processing(photo_id, self.test_token, timeout=30)

		response = requests.get(f"{API_URL}/users/{user_id}/photos")
		assert response.status_code == 200
		data = response.json()

		if data["photos"]:
			photo = data["photos"][0]
			# Check expected fields
			expected_fields = ["id", "uploaded_at", "processing_status"]
			for field in expected_fields:
				assert field in photo, f"Missing field: {field}"


if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
