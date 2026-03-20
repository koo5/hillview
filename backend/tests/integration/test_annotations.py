#!/usr/bin/env python3
"""
Tests for photo annotation API endpoints.

Covers:
- POST /api/annotations/photos/{photo_id} (create)
- GET /api/annotations/photos/{photo_id} (list)
- PUT /api/annotations/{id} (update / supersede)
- DELETE /api/annotations/{id} (tombstone delete)
- Hidden user filtering in annotation listing
- Supersede chain conflict detection (409)
"""

import requests
import os
import sys

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest
from utils.test_utils import API_URL, query_hillview_endpoint


class TestAnnotationCRUD(BaseUserManagementTest):
    """Test basic annotation CRUD operations."""

    def setup_method(self, method=None):
        super().setup_method(method)
        # Upload test photos so we have a photo_id to annotate
        self.create_test_photos(self.test_users, self.auth_tokens)
        # Grab the first available photo
        result = query_hillview_endpoint(token=self.test_token, params={
            "top_left_lat": 90, "top_left_lon": -180,
            "bottom_right_lat": -90, "bottom_right_lon": 180,
            "client_id": "test_annotations",
        })
        assert result and result.get("data"), "No photos after create_test_photos — check worker"
        self.photo_id = result["data"][0]["id"]

    def test_create_annotation(self):
        """Test creating a new annotation."""
        response = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={
                "body": "Test annotation",
                "target": {
                    "selector": {
                        "type": "RECTANGLE",
                        "geometry": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
                    }
                },
            },
            headers=self.test_headers,
        )
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["body"] == "Test annotation"
        assert data["is_current"] is True
        assert data["event_type"] == "created"
        assert data["photo_id"] == self.photo_id

    def test_create_annotation_on_nonexistent_photo(self):
        """Creating annotation on missing photo returns 404."""
        response = requests.post(
            f"{API_URL}/annotations/photos/nonexistent-id",
            json={"body": "Orphan annotation"},
            headers=self.test_headers,
        )
        assert response.status_code == 404

    def test_create_annotation_unauthenticated(self):
        """Creating annotation without auth returns 401."""
        response = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "No auth"},
        )
        assert response.status_code in (401, 403)

    def test_list_annotations(self):
        """Test listing annotations for a photo."""
        # Create an annotation first
        requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Listing test"},
            headers=self.test_headers,
        )

        # List (unauthenticated — should still work)
        response = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        bodies = [a["body"] for a in data]
        assert "Listing test" in bodies

    def test_update_annotation_supersedes(self):
        """Updating an annotation creates a new version and supersedes the old one."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Original"},
            headers=self.test_headers,
        )
        assert create_resp.status_code == 201
        original_id = create_resp.json()["id"]

        update_resp = requests.put(
            f"{API_URL}/annotations/{original_id}",
            json={"body": "Updated"},
            headers=self.test_headers,
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["body"] == "Updated"
        assert updated["event_type"] == "updated"
        assert updated["is_current"] is True
        assert updated["id"] != original_id

    def test_update_already_superseded_returns_409(self):
        """Updating a non-current annotation returns 409."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Will be superseded"},
            headers=self.test_headers,
        )
        original_id = create_resp.json()["id"]

        requests.put(
            f"{API_URL}/annotations/{original_id}",
            json={"body": "Superseded version"},
            headers=self.test_headers,
        )

        response = requests.put(
            f"{API_URL}/annotations/{original_id}",
            json={"body": "Should fail"},
            headers=self.test_headers,
        )
        assert response.status_code == 409

    def test_delete_annotation_creates_tombstone(self):
        """Deleting an annotation creates a tombstone and hides it from listings."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "To be deleted"},
            headers=self.test_headers,
        )
        ann_id = create_resp.json()["id"]

        delete_resp = requests.delete(
            f"{API_URL}/annotations/{ann_id}",
            headers=self.test_headers,
        )
        assert delete_resp.status_code == 204

        list_resp = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}")
        assert list_resp.status_code == 200
        bodies = [a["body"] for a in list_resp.json()]
        assert "To be deleted" not in bodies

    def test_delete_already_superseded_returns_409(self):
        """Deleting a non-current annotation returns 409."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Will be superseded then deleted"},
            headers=self.test_headers,
        )
        ann_id = create_resp.json()["id"]

        requests.put(
            f"{API_URL}/annotations/{ann_id}",
            json={"body": "New version"},
            headers=self.test_headers,
        )

        response = requests.delete(
            f"{API_URL}/annotations/{ann_id}",
            headers=self.test_headers,
        )
        assert response.status_code == 409

    def test_delete_nonexistent_returns_404(self):
        """Deleting a nonexistent annotation returns 404."""
        response = requests.delete(
            f"{API_URL}/annotations/nonexistent-uuid",
            headers=self.test_headers,
        )
        assert response.status_code == 404


class TestAnnotationHiddenUserFiltering(BaseUserManagementTest):
    """Test that hidden user annotations are filtered from listings."""

    def setup_method(self, method=None):
        super().setup_method(method)
        self.create_test_photos(self.test_users, self.auth_tokens)
        result = query_hillview_endpoint(token=self.test_token, params={
            "top_left_lat": 90, "top_left_lon": -180,
            "bottom_right_lat": -90, "bottom_right_lon": 180,
            "client_id": "test_annotations_filter",
        })
        assert result and result.get("data"), "No photos after create_test_photos — check worker"
        self.photo_id = result["data"][0]["id"]

    def test_hidden_user_annotations_filtered(self):
        """Annotations by hidden users should not appear in listing."""
        # Admin creates an annotation
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Admin annotation for filtering test"},
            headers=self.admin_headers,
        )
        assert create_resp.status_code == 201
        admin_ann = create_resp.json()
        admin_user_id = admin_ann["user_id"]

        # Visible in unauthenticated listing
        list_resp = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}")
        bodies = [a["body"] for a in list_resp.json()]
        assert "Admin annotation for filtering test" in bodies

        # Test user hides the admin user
        hide_resp = requests.post(
            f"{API_URL}/hidden/users",
            json={
                "target_user_source": "hillview",
                "target_user_id": admin_user_id,
                "reason": "Test filtering",
            },
            headers=self.test_headers,
        )
        assert hide_resp.status_code == 200, f"Failed to hide user: {hide_resp.text}"

        # Now list as the test user — admin's annotation should be filtered out
        list_resp = requests.get(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            headers=self.test_headers,
        )
        assert list_resp.status_code == 200
        bodies = [a["body"] for a in list_resp.json()]
        assert "Admin annotation for filtering test" not in bodies, \
            f"Hidden user's annotation should not appear. Got bodies: {bodies}"

        # Cleanup: unhide the admin user
        requests.delete(
            f"{API_URL}/hidden/users",
            json={
                "target_user_source": "hillview",
                "target_user_id": admin_user_id,
            },
            headers=self.test_headers,
        )
