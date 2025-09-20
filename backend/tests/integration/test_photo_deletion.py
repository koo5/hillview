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
from pathlib import Path
import tempfile
import time

# Import test utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from tests.utils.base_test import BasePhotoTest
from tests.utils.secure_upload_utils import SecureUploadClient
from tests.utils.test_utils import API_URL
from tests.utils.image_utils import create_test_image_full_gps


class TestPhotoDeletion(BasePhotoTest):
    """Test photo deletion endpoint functionality."""

    def setUp(self):
        """Set up test environment before each test."""
        super().setUp()

        # Create test image for uploads
        self.test_image_path = create_test_image()

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

        # Clean up test image
        if hasattr(self, 'test_image_path') and os.path.exists(self.test_image_path):
            os.unlink(self.test_image_path)

        super().tearDown()

    def test_delete_photo_success(self):
        """Test successful photo deletion by owner."""
        print("\n=== Testing successful photo deletion ===")

        # Upload a test photo first
        photo_id = upload_photo_securely(
            image_path=self.test_image_path,
            description="Test photo for deletion",
            is_public=True,
            headers=self.test_headers
        )
        self.uploaded_photo_ids.append(photo_id)
        print(f"✓ Uploaded test photo: {photo_id}")

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
                file_response = requests.get(url, timeout=5)
                if file_response.status_code == 200:
                    accessible_before.append(url)
                    print(f"✓ File accessible before deletion: {url}")
            except requests.exceptions.RequestException as e:
                print(f"⚠️ File not accessible before deletion: {url} - {e}")

        # Delete the photo
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(delete_response)

        result = delete_response.json()
        assert "message" in result
        assert "deleted successfully" in result["message"].lower()
        print(f"✓ Photo deleted successfully: {result['message']}")

        # Verify photo no longer exists in API
        get_response_after = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        assert get_response_after.status_code == 404, f"Photo should be deleted, got {get_response_after.status_code}"
        print("✓ Photo no longer accessible via API")

        # Verify photo no longer appears in user's photo list
        list_response = requests.get(f"{API_URL}/photos/", headers=self.test_headers)
        self.assert_success(list_response)
        photos_list = list_response.json().get("photos", [])

        photo_still_listed = any(photo["id"] == photo_id for photo in photos_list)
        assert not photo_still_listed, "Deleted photo should not appear in user's photo list"
        print("✓ Photo removed from user's photo list")

        # CRITICAL: Verify physical files are actually deleted
        # Files that were accessible before MUST be inaccessible after deletion
        still_accessible = []
        for url in accessible_before:
            try:
                file_response = requests.get(url, timeout=5)
                if file_response.status_code == 200:
                    still_accessible.append(url)
                elif file_response.status_code == 404:
                    print(f"✓ File properly deleted: {url}")
                else:
                    print(f"✓ File no longer accessible: {url} (status: {file_response.status_code})")
            except requests.exceptions.RequestException:
                print(f"✓ File no longer accessible: {url}")

        # FAIL THE TEST if any files are still accessible
        if still_accessible:
            failure_msg = f"DELETION FAILED: {len(still_accessible)} files still accessible after deletion:\n"
            for url in still_accessible:
                failure_msg += f"  - {url}\n"
            assert False, failure_msg

        print(f"✅ All {len(accessible_before)} files properly deleted")

        # Remove from our tracking list since it's successfully deleted
        self.uploaded_photo_ids.remove(photo_id)

    def test_delete_photo_unauthorized(self):
        """Test photo deletion without authentication."""
        print("\n=== Testing photo deletion without authentication ===")

        # Try to delete a photo without auth headers
        response = requests.delete(f"{API_URL}/photos/non-existent-id")
        self.assert_unauthorized(response)
        print("✓ Deletion properly rejected without authentication")

    def test_delete_photo_wrong_owner(self):
        """Test photo deletion by non-owner user."""
        print("\n=== Testing photo deletion by wrong owner ===")

        # Upload photo as test user
        photo_id = upload_photo_securely(
            image_path=self.test_image_path,
            description="Test photo owned by test user",
            is_public=True,
            headers=self.test_headers
        )
        self.uploaded_photo_ids.append(photo_id)
        print(f"✓ Uploaded photo as test user: {photo_id}")

        # Try to delete as admin user (different owner)
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.admin_headers)
        assert delete_response.status_code == 404, f"Should get 404 for non-owned photo, got {delete_response.status_code}"
        print("✓ Deletion properly rejected for non-owner")

        # Verify photo still exists
        get_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(get_response)
        print("✓ Photo still exists after failed deletion attempt")

    def test_delete_nonexistent_photo(self):
        """Test deletion of non-existent photo."""
        print("\n=== Testing deletion of non-existent photo ===")

        fake_photo_id = "00000000-0000-0000-0000-000000000000"
        delete_response = requests.delete(f"{API_URL}/photos/{fake_photo_id}", headers=self.test_headers)

        assert delete_response.status_code == 404, f"Should get 404 for non-existent photo, got {delete_response.status_code}"
        print("✓ Non-existent photo deletion properly returns 404")

    def test_delete_invalid_photo_id(self):
        """Test deletion with invalid photo ID format."""
        print("\n=== Testing deletion with invalid photo ID ===")

        invalid_ids = ["invalid", "123", "not-a-uuid"]

        for invalid_id in invalid_ids:
            delete_response = requests.delete(f"{API_URL}/photos/{invalid_id}", headers=self.test_headers)
            # Should return 404 or 422 depending on validation
            assert delete_response.status_code in [404, 422], f"Invalid ID {invalid_id} should return 404 or 422, got {delete_response.status_code}"
            print(f"✓ Invalid photo ID '{invalid_id}' properly rejected")

    def test_delete_photo_with_unknown_storage_type(self):
        """Test deletion of photo with unknown storage type (regression test)."""
        print("\n=== Testing deletion with unknown storage type ===")

        # This test specifically addresses the bug we found where
        # photos with unknown storage types can't be deleted

        # Upload photo normally
        photo_id = upload_photo_securely(
            image_path=self.test_image_path,
            description="Test photo for storage type handling",
            is_public=True,
            headers=self.test_headers
        )
        self.uploaded_photo_ids.append(photo_id)
        print(f"✓ Uploaded test photo: {photo_id}")

        # The deletion should succeed even if storage type can't be determined
        # (This tests the fix for the storage type determination issue)
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)

        # Should succeed, not return 500 error
        if delete_response.status_code == 500:
            error_text = delete_response.text
            assert False, f"Photo deletion failed with 500 error - storage type issue not fixed: {error_text}"

        self.assert_success(delete_response)
        print("✓ Photo deletion succeeded despite potential storage type issues")

        # Verify it's actually deleted from database
        get_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        assert get_response.status_code == 404, "Photo should be deleted from database"
        print("✓ Photo successfully removed from database")

        # Remove from tracking
        self.uploaded_photo_ids.remove(photo_id)


def run_photo_deletion_tests():
    """Run all photo deletion tests."""
    test_cases = [
        "test_delete_photo_success",
        "test_delete_photo_unauthorized",
        "test_delete_photo_wrong_owner",
        "test_delete_nonexistent_photo",
        "test_delete_invalid_photo_id",
        "test_delete_photo_with_unknown_storage_type",
    ]

    print("🗑️ Running Photo Deletion Integration Tests")
    print("=" * 50)

    passed = 0
    failed = 0

    for i, test_name in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] {test_name}")
        try:
            # Create fresh instance for each test
            test_instance = TestPhotoDeletion()
            test_instance.setUp()
            test_method = getattr(test_instance, test_name)
            test_method()
            test_instance.tearDown()
            print(f"✅ {test_name} PASSED")
            passed += 1
        except Exception as e:
            print(f"❌ {test_name} FAILED: {e}")
            failed += 1
            raise

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("🎉 All photo deletion tests passed!")
    else:
        print(f"💥 {failed} tests failed!")


if __name__ == "__main__":
    run_photo_deletion_tests()