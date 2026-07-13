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
import unittest
import pytest

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

    def _audit_entries_for(self, photo_id: str, token: str) -> list:
        """Return moderation-audit entries for a photo id (via the admin/moderator read API)."""
        response = requests.get(
            f"{API_URL}/photos/moderation-audit",
            params={"limit": 200},
            headers=self.get_auth_headers(token),
        )
        self.assert_success(response, "Should be able to read moderation audit")
        return [e for e in response.json()["entries"] if e["photo_id"] == photo_id]

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
        """A regular (non-admin) user cannot delete another user's photo."""
        print("\n=== Testing photo deletion by wrong owner (regular user) ===")

        # Upload photo as test user
        photo_id = await self._create_test_photo("test_delete_wrong_owner.jpg", "Test photo owned by test user")
        print(f"✓ Uploaded test photo as test user: {photo_id}")

        # Try to delete as a different *regular* user (no admin/moderator rights)
        other_token = self.get_test_token("testuser")
        other_headers = self.get_auth_headers(other_token)
        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=other_headers)
        assert delete_response.status_code == 404, "Non-owner regular user should get 404 (existence hidden)"
        print("✓ Properly rejected deletion by non-owner regular user (404)")

        # Verify photo still exists
        get_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(get_response)
        print("✓ Photo still exists after failed unauthorized deletion")

        # And the denied attempt must NOT leave an audit entry
        entries = self._audit_entries_for(photo_id, self.get_admin_token())
        assert entries == [], "A denied deletion must not create a moderation-audit entry"
        print("✓ No moderation-audit entry created by the denied deletion")

    @pytest.mark.asyncio
    async def test_admin_can_delete_others_photo_with_audit(self):
        """An admin can delete another user's photo, and it is recorded in the moderation audit."""
        print("\n=== Testing admin deletion of another user's photo (with audit) ===")

        photo_id = await self._create_test_photo("test_admin_delete.jpg", "Test photo owned by test user")
        wait_for_photo_processing(photo_id, self.test_token, timeout=30)
        print(f"✓ Uploaded test photo as test user: {photo_id}")

        admin_token = self.get_admin_token()
        admin_headers = self.get_auth_headers(admin_token)

        reason = "integration test: inappropriate content"
        delete_response = requests.delete(
            f"{API_URL}/photos/{photo_id}",
            params={"reason": reason},
            headers=admin_headers,
        )
        self.assert_success(delete_response, "Admin should be able to delete another user's photo")
        print("✓ Admin deletion succeeded (200)")

        # Owner can no longer access the photo
        get_after = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        assert get_after.status_code == 404, "Photo should be gone after admin deletion"
        print("✓ Photo no longer visible to its owner")

        # Exactly one audit entry, describing the moderation action
        entries = self._audit_entries_for(photo_id, admin_token)
        assert len(entries) == 1, f"Expected exactly one audit entry, got {len(entries)}"
        entry = entries[0]
        assert entry["action"] == "delete", entry
        assert entry["actor_username"] == "admin", entry
        assert entry["actor_role"] == "admin", entry
        assert entry["photo_owner_username"] == "test", entry
        assert entry["reason"] == reason, entry
        print("✓ Moderation-audit entry recorded with actor, owner and reason")

        # Already deleted — drop from teardown tracking
        if photo_id in self.uploaded_photo_ids:
            self.uploaded_photo_ids.remove(photo_id)

    @pytest.mark.asyncio
    async def test_owner_delete_creates_no_audit(self):
        """An owner deleting their own photo must NOT create a moderation-audit entry."""
        print("\n=== Testing owner self-deletion creates no audit ===")

        photo_id = await self._create_test_photo("test_owner_delete_noaudit.jpg", "Owner-deleted photo")
        wait_for_photo_processing(photo_id, self.test_token, timeout=30)

        delete_response = requests.delete(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
        self.assert_success(delete_response)
        print("✓ Owner deleted their own photo (200)")

        entries = self._audit_entries_for(photo_id, self.get_admin_token())
        assert entries == [], "Owner self-deletion must not be recorded in the moderation audit"
        print("✓ No moderation-audit entry for owner self-deletion")

        if photo_id in self.uploaded_photo_ids:
            self.uploaded_photo_ids.remove(photo_id)

    def test_moderation_audit_requires_privilege(self):
        """The moderation-audit listing is restricted to admins/moderators."""
        print("\n=== Testing moderation-audit access control ===")

        # Regular user is forbidden
        resp = requests.get(f"{API_URL}/photos/moderation-audit", headers=self.test_headers)
        assert resp.status_code == 403, f"Regular user should be forbidden, got {resp.status_code}"
        print("✓ Regular user forbidden (403)")

        # Unauthenticated is rejected
        resp = requests.get(f"{API_URL}/photos/moderation-audit")
        assert resp.status_code == 401, f"Unauthenticated should be 401, got {resp.status_code}"
        print("✓ Unauthenticated rejected (401)")

        # Admin can read
        resp = requests.get(
            f"{API_URL}/photos/moderation-audit",
            headers=self.get_auth_headers(self.get_admin_token()),
        )
        self.assert_success(resp)
        assert "entries" in resp.json()
        print("✓ Admin can read the moderation audit")

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