#!/usr/bin/env python3
"""
Tests for flagged photos endpoints.

Covers:
- POST /api/flagged/photos (flag a photo)
- DELETE /api/flagged/photos (unflag a photo)
- GET /api/flagged/photos (list user's flagged photos)
- GET /api/flagged/photos/all (admin only - list all flags)
- POST /api/flagged/resolve (admin only - resolve a flag)
- Authentication and authorization
- Input validation
"""

import requests
import os
import sys

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest
from utils.test_utils import API_URL


class TestFlagPhoto(BaseUserManagementTest):
    """Test suite for photo flagging endpoints."""

    def setup_method(self, method=None):
        """Set up test with photo IDs."""
        super().setup_method(method)
        self.test_photo_id = "test_flag_photo_123"
        print("Setting up flagged photos tests...")

    def test_flag_photo_success(self):
        """Test successfully flagging a photo."""
        print("\n--- Testing Flag Photo Success ---")

        response = requests.post(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "mapillary",
                "photo_id": self.test_photo_id,
                "reason": "Test flagging reason"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert "flagged successfully" in data.get("message", ""), f"Expected success message, got {data}"

        print("✓ Photo flagged successfully")

    def test_flag_photo_duplicate(self):
        """Test flagging a photo that's already flagged by same user."""
        print("\n--- Testing Duplicate Flag ---")

        flag_request = {
            "photo_source": "mapillary",
            "photo_id": "duplicate_test_photo",
            "reason": "Initial flag"
        }

        # First flag
        response1 = requests.post(
            f"{API_URL}/flagged/photos",
            json=flag_request,
            headers=self.test_headers
        )
        assert response1.status_code == 200, f"First flag failed: {response1.status_code}"
        print("✓ Photo flagged initially")

        # Second flag (duplicate)
        flag_request["reason"] = "Duplicate attempt"
        response2 = requests.post(
            f"{API_URL}/flagged/photos",
            json=flag_request,
            headers=self.test_headers
        )

        print(f"Duplicate response status: {response2.status_code}")
        print(f"Duplicate response: {response2.json()}")

        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}"

        data = response2.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert data.get("already_flagged") is True, f"Expected already_flagged=True, got {data}"

        print("✓ Duplicate flagging handled correctly")

    def test_flag_photo_hillview_source(self):
        """Test flagging a hillview photo."""
        print("\n--- Testing Flag Hillview Photo ---")

        response = requests.post(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "hillview",
                "photo_id": "hillview_test_photo",
                "reason": "Test hillview flagging"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Hillview photo flagged successfully")

    def test_flag_photo_invalid_source(self):
        """Test flagging with invalid photo source."""
        print("\n--- Testing Invalid Photo Source ---")

        response = requests.post(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "invalid_source",
                "photo_id": "test_photo",
                "reason": "Test"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Invalid photo source rejected correctly")

    def test_flag_photo_requires_auth(self):
        """Test that flagging requires authentication."""
        print("\n--- Testing Flag Requires Auth ---")

        response = requests.post(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "mapillary",
                "photo_id": "test_photo"
            }
            # No auth headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Authentication required for flagging")

    def test_flag_photo_missing_fields(self):
        """Test validation of required fields."""
        print("\n--- Testing Missing Fields ---")

        # Missing photo_id
        response = requests.post(
            f"{API_URL}/flagged/photos",
            json={"photo_source": "mapillary"},
            headers=self.test_headers
        )
        assert response.status_code == 422, f"Expected 422 for missing photo_id, got {response.status_code}"
        print("✓ Missing photo_id rejected")

        # Missing photo_source
        response = requests.post(
            f"{API_URL}/flagged/photos",
            json={"photo_id": "test"},
            headers=self.test_headers
        )
        assert response.status_code == 422, f"Expected 422 for missing photo_source, got {response.status_code}"
        print("✓ Missing photo_source rejected")


class TestUnflagPhoto(BaseUserManagementTest):
    """Test suite for photo unflagging."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        self.test_photo_id = "unflag_test_photo"
        print("Setting up unflag tests...")

    def test_unflag_photo_success(self):
        """Test successfully unflagging a photo."""
        print("\n--- Testing Unflag Photo Success ---")

        # First flag the photo
        requests.post(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "mapillary",
                "photo_id": self.test_photo_id,
                "reason": "Setup for unflag test"
            },
            headers=self.test_headers
        )
        print("✓ Photo flagged for unflag test")

        # Now unflag
        response = requests.delete(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "mapillary",
                "photo_id": self.test_photo_id
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert "unflagged successfully" in data.get("message", ""), f"Expected success message, got {data}"

        print("✓ Photo unflagged successfully")

    def test_unflag_photo_not_flagged(self):
        """Test unflagging a photo that wasn't flagged."""
        print("\n--- Testing Unflag Not Flagged Photo ---")

        response = requests.delete(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "mapillary",
                "photo_id": "never_flagged_photo"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert data.get("already_flagged") is False, f"Expected already_flagged=False, got {data}"

        print("✓ Unflagging non-flagged photo handled correctly")

    def test_unflag_photo_requires_auth(self):
        """Test that unflagging requires authentication."""
        print("\n--- Testing Unflag Requires Auth ---")

        response = requests.delete(
            f"{API_URL}/flagged/photos",
            json={
                "photo_source": "mapillary",
                "photo_id": "test_photo"
            }
            # No auth headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Authentication required for unflagging")


class TestListFlaggedPhotos(BaseUserManagementTest):
    """Test suite for listing flagged photos."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        print("Setting up list flagged photos tests...")

    def test_list_flagged_photos_empty(self):
        """Test listing flagged photos when none exist."""
        print("\n--- Testing List Flagged Photos (Empty) ---")

        response = requests.get(
            f"{API_URL}/flagged/photos",
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"

        print(f"✓ Listed {len(data)} flagged photos")

    def test_list_flagged_photos_with_data(self):
        """Test listing flagged photos after flagging some."""
        print("\n--- Testing List Flagged Photos (With Data) ---")

        # Flag a couple of photos
        for i in range(2):
            requests.post(
                f"{API_URL}/flagged/photos",
                json={
                    "photo_source": "mapillary",
                    "photo_id": f"list_test_photo_{i}",
                    "reason": f"Test reason {i}"
                },
                headers=self.test_headers
            )

        # List flagged photos
        response = requests.get(
            f"{API_URL}/flagged/photos",
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) >= 2, f"Expected at least 2 flagged photos, got {len(data)}"

        # Verify structure
        if data:
            photo = data[0]
            required_fields = ["photo_source", "photo_id", "flagged_at", "reason"]
            for field in required_fields:
                assert field in photo, f"Missing field '{field}' in response"

        print(f"✓ Listed {len(data)} flagged photos with correct structure")

    def test_list_flagged_photos_filter_by_source(self):
        """Test filtering flagged photos by source."""
        print("\n--- Testing List With Source Filter ---")

        # Flag photos from different sources
        requests.post(
            f"{API_URL}/flagged/photos",
            json={"photo_source": "mapillary", "photo_id": "filter_mapillary"},
            headers=self.test_headers
        )
        requests.post(
            f"{API_URL}/flagged/photos",
            json={"photo_source": "hillview", "photo_id": "filter_hillview"},
            headers=self.test_headers
        )

        # Filter by mapillary
        response = requests.get(
            f"{API_URL}/flagged/photos",
            params={"photo_source": "mapillary"},
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        for photo in data:
            assert photo["photo_source"] == "mapillary", f"Expected only mapillary photos, got {photo['photo_source']}"

        print("✓ Source filtering works correctly")

    def test_list_flagged_photos_requires_auth(self):
        """Test that listing requires authentication."""
        print("\n--- Testing List Requires Auth ---")

        response = requests.get(f"{API_URL}/flagged/photos")

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Authentication required for listing")


class TestAdminFlaggedPhotos(BaseUserManagementTest):
    """Test suite for admin flagged photo endpoints."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        print("Setting up admin flagged photos tests...")

    def test_list_all_flagged_requires_admin(self):
        """Test that listing all flags requires admin role."""
        print("\n--- Testing List All Requires Admin ---")

        # Try as regular user
        response = requests.get(
            f"{API_URL}/flagged/photos/all",
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Regular user rejected from admin endpoint")

    def test_list_all_flagged_no_auth(self):
        """Test that listing all flags requires authentication."""
        print("\n--- Testing List All Requires Auth ---")

        response = requests.get(f"{API_URL}/flagged/photos/all")

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Authentication required for admin listing")

    def test_resolve_flag_requires_admin(self):
        """Test that resolving flags requires admin role."""
        print("\n--- Testing Resolve Requires Admin ---")

        # Try as regular user
        response = requests.post(
            f"{API_URL}/flagged/resolve",
            json={"flag_id": "some_flag_id"},
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Regular user rejected from resolve endpoint")

    def test_resolve_flag_no_auth(self):
        """Test that resolving flags requires authentication."""
        print("\n--- Testing Resolve Requires Auth ---")

        response = requests.post(
            f"{API_URL}/flagged/resolve",
            json={"flag_id": "some_flag_id"}
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Authentication required for resolving")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
