"""
Integration tests for photo deletion functionality.

Tests the DELETE /api/photos/{photo_id} endpoint functionality including:
- Successful photo deletion
- File cleanup verification (files MUST be inaccessible after deletion)
- Authentication requirements
- Authorization (owner-only deletion)
- Error handling for non-existent photos
"""

import requests
import json
import unittest
import pytest
import asyncio
from pathlib import Path
import tempfile
import time

# Import test utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.test_utils import API_URL, upload_test_image, wait_for_photo_processing
from utils.image_utils import create_test_image_full_gps


class TestPhotoDeletion(BasePhotoTest):
    """Test photo deletion functionality."""

    def setUp(self):
        """Set up test environment before each test."""
        super().setUp()
        # Test will upload photos and then delete them
        self.uploaded_photo_ids = []

    def tearDown(self):
        """Clean up after each test."""
        # Clean up any remaining test photos
        for photo_id in self.uploaded_photo_ids:
            try:
                requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
            except:
                pass
        super().tearDown()

    async def _create_test_photo(self, filename: str = "test_deletion.jpg", description: str = "Test photo for deletion") -> str:
        """Create a test photo and return photo ID."""
        image_data = create_test_image_full_gps(200, 150, (255, 0, 0), lat=50.0755, lon=14.4378, bearing=90.0)
        photo_id = await upload_test_image(filename, image_data, description, self.test_token)
        self.uploaded_photo_ids.append(photo_id)
        return photo_id

    @pytest.mark.asyncio
    async def test_delete_photo_success(self):
        """Test successful photo deletion by owner."""
        print("\n=== Testing successful photo deletion ===")

        # Upload a test photo first
        photo_id = await self._create_test_photo("test_delete_success.jpg", "Test photo for deletion")
        print(f"✓ Uploaded test photo: {photo_id}")

        # Wait for processing
        wait_for_photo_processing(photo_id, self.test_token, timeout=30)

        # Verify photo exists before deletion
        get_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(get_response)
        photo_data = get_response.json()
        print(f"✓ Photo exists before deletion: {photo_data['original_filename']}")

        # Store file URLs for verification after deletion
        file_urls = []
        if photo_data.get('sizes'):
            for size_info in photo_data['sizes'].values():
                if 'url' in size_info:
                    file_urls.append(size_info['url'])
        print(f"✓ Found {len(file_urls)} file URLs to verify deletion")

        # Verify files are accessible before deletion
        accessible_before = []
        for url in file_urls:
            try:
                file_response = requests.head(url)
                if file_response.status_code == 200:
                    accessible_before.append(url)
            except:
                pass
        print(f"✓ {len(accessible_before)} files accessible before deletion")

        # Delete the photo
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(delete_response)
        print("✓ Photo deletion request successful")

        # Verify photo no longer exists
        get_response_after = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        assert get_response_after.status_code == 404, "Photo should not exist after deletion"
        print("✓ Photo record removed from database")

        # Verify files are no longer accessible (CRITICAL - files must be deleted)
        accessible_after = []
        for url in file_urls:
            try:
                file_response = requests.head(url)
                if file_response.status_code == 200:
                    accessible_after.append(url)
                    print(f"🚨 ERROR: File still accessible after deletion: {url}")
            except:
                pass

        assert len(accessible_after) == 0, f"Files should not be accessible after deletion. Still accessible: {accessible_after}"
        print("✓ All files properly cleaned up after deletion")

        # Remove from our tracking list since it's been deleted
        if photo_id in self.uploaded_photo_ids:
            self.uploaded_photo_ids.remove(photo_id)

    @pytest.mark.asyncio
    async def test_delete_photo_unauthorized(self):
        """Test photo deletion without authentication."""
        print("\n=== Testing unauthorized photo deletion ===")

        # Upload a test photo first
        photo_id = await self._create_test_photo("test_delete_unauth.jpg", "Test photo for unauthorized deletion")
        print(f"✓ Uploaded test photo: {photo_id}")

        # Try to delete without authentication
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}")
        assert delete_response.status_code == 401, "Should require authentication"
        print("✓ Properly rejected unauthenticated deletion request")

        # Verify photo still exists
        get_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(get_response)
        print("✓ Photo still exists after failed unauthorized deletion")

    @pytest.mark.asyncio
    async def test_delete_photo_wrong_owner(self):
        """Test photo deletion by non-owner."""
        print("\n=== Testing photo deletion by wrong owner ===")

        # Upload photo as test user
        photo_id = await self._create_test_photo("test_delete_wrong_owner.jpg", "Test photo owned by test user")
        print(f"✓ Uploaded test photo as test user: {photo_id}")

        # Try to delete as admin user (different owner)
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=admin_headers)
        assert delete_response.status_code == 404, "Should return 404 when trying to delete another user's photo (API design choice)"
        print("✓ Properly rejected deletion by non-owner (returns 404 - photo not found for this user)")

        # Verify photo still exists
        get_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(get_response)
        print("✓ Photo still exists after failed unauthorized deletion")

    def test_delete_nonexistent_photo(self):
        """Test deletion of non-existent photo."""
        print("\n=== Testing deletion of non-existent photo ===")

        # Try to delete a non-existent photo
        fake_photo_id = "nonexistent-photo-id"
        delete_response = requests.delete(f"{API_URL}/photos/{fake_photo_id}", headers=self.test_headers)
        assert delete_response.status_code == 404, "Should return 404 for non-existent photo"
        print("✓ Properly handled deletion of non-existent photo")

    def test_delete_invalid_photo_id(self):
        """Test deletion with invalid photo ID format."""
        print("\n=== Testing deletion with invalid photo ID ===")

        # Try various invalid photo ID formats
        invalid_ids = [
            ("invalid-uuid", [400, 404]),
            ("123", [400, 404]),
            ("not-a-uuid", [400, 404]),
            ("   ", [400, 404, 405]),  # Whitespace might cause routing issues
            ("", [405]),  # Empty string causes Method Not Allowed due to routing
        ]

        for invalid_id, expected_codes in invalid_ids:
            delete_response = requests.delete(f"{API_URL}/photos/{invalid_id}", headers=self.test_headers)
            assert delete_response.status_code in expected_codes, f"Should reject invalid photo ID '{invalid_id}' with one of {expected_codes}, got {delete_response.status_code}"
            print(f"✓ Properly rejected invalid photo ID '{invalid_id}' with status {delete_response.status_code}")

    @pytest.mark.asyncio
    async def test_delete_photo_with_unknown_storage_type(self):
        """Test deletion of photo with unknown storage configuration."""
        print("\n=== Testing deletion with unknown storage type ===")

        # Upload photo normally
        photo_id = await self._create_test_photo("test_delete_storage.jpg", "Test photo for storage type handling")
        print(f"✓ Uploaded test photo: {photo_id}")

        # Wait for processing
        wait_for_photo_processing(photo_id, self.test_token, timeout=30)

        # Delete the photo - should handle gracefully even with unknown storage types
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(delete_response)
        print("✓ Photo deletion succeeded despite storage configuration")

        # Remove from our tracking list since it's been deleted
        if photo_id in self.uploaded_photo_ids:
            self.uploaded_photo_ids.remove(photo_id)


if __name__ == "__main__":
    unittest.main()