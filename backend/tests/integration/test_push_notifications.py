#!/usr/bin/env python3
"""
Tests for push notification endpoints.

Covers:
- POST /api/push/register (register push endpoint)
- DELETE /api/push/unregister/{client_key_id} (unregister)
- GET /api/notifications/recent (get user notifications)
- GET /api/notifications/unread-count (get unread count)
- PUT /api/notifications/read (mark as read)
- Internal notification endpoints
- ECDSA signature verification
- Authentication and authorization
"""

import requests
import os
import sys
import time
import pytest

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest
from utils.test_utils import API_URL
from utils.crypto_utils import (
    generate_ecdsa_key_pair,
    serialize_private_key,
    serialize_public_key,
    generate_client_key_id,
    generate_push_signature,
)


class TestNotificationEndpoints(BaseUserManagementTest):
    """Test suite for notification CRUD endpoints."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        print("Setting up notification endpoint tests...")

    def test_get_recent_notifications_empty(self):
        """Test getting notifications when none exist."""
        print("\n--- Testing Get Recent Notifications (Empty) ---")

        response = requests.get(
            f"{API_URL}/notifications/recent",
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert "notifications" in data, f"Expected 'notifications' in response, got {data}"
        assert "total_count" in data, f"Expected 'total_count' in response, got {data}"
        assert "unread_count" in data, f"Expected 'unread_count' in response, got {data}"
        assert isinstance(data["notifications"], list), f"Expected list, got {type(data['notifications'])}"

        print(f"Got {len(data['notifications'])} notifications (total: {data['total_count']}, unread: {data['unread_count']})")

    def test_get_recent_notifications_requires_auth(self):
        """Test that getting notifications requires authentication."""
        print("\n--- Testing Get Recent Notifications Requires Auth ---")

        response = requests.get(f"{API_URL}/notifications/recent")

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Authentication required for getting notifications")

    def test_get_unread_count(self):
        """Test getting unread notification count."""
        print("\n--- Testing Get Unread Count ---")

        response = requests.get(
            f"{API_URL}/notifications/unread-count",
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert "unread_count" in data, f"Expected 'unread_count' in response, got {data}"
        assert isinstance(data["unread_count"], int), f"Expected int, got {type(data['unread_count'])}"

        print(f"Unread count: {data['unread_count']}")

    def test_get_unread_count_requires_auth(self):
        """Test that getting unread count requires authentication."""
        print("\n--- Testing Get Unread Count Requires Auth ---")

        response = requests.get(f"{API_URL}/notifications/unread-count")

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Authentication required for getting unread count")

    def test_mark_notifications_read_empty(self):
        """Test marking notifications as read with empty list."""
        print("\n--- Testing Mark Notifications Read (Empty) ---")

        response = requests.put(
            f"{API_URL}/notifications/read",
            json={"notification_ids": []},
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"

        print("Empty notification list handled correctly")

    def test_mark_notifications_read_requires_auth(self):
        """Test that marking notifications as read requires authentication."""
        print("\n--- Testing Mark Notifications Read Requires Auth ---")

        response = requests.put(
            f"{API_URL}/notifications/read",
            json={"notification_ids": [1, 2, 3]}
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Authentication required for marking notifications as read")

    def test_mark_nonexistent_notifications_read(self):
        """Test marking non-existent notifications as read."""
        print("\n--- Testing Mark Non-existent Notifications Read ---")

        response = requests.put(
            f"{API_URL}/notifications/read",
            json={"notification_ids": [999999, 999998]},
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        # Should succeed but update 0 notifications
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"

        print("Non-existent notifications handled gracefully")


class TestPushRegistration(BaseUserManagementTest):
    """Test suite for push registration endpoints."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        self.key_pair = None
        print("Setting up push registration tests...")

    def _generate_key_pair(self):
        """Generate ECDSA key pair for testing."""
        if not self.key_pair:
            private_key, public_key = generate_ecdsa_key_pair()
            self.key_pair = {
                "private_key": private_key,
                "public_key": public_key,
                "private_pem": serialize_private_key(private_key),
                "public_pem": serialize_public_key(public_key)
            }
        return self.key_pair

    def test_register_push_success(self):
        """Test successfully registering a push endpoint."""
        print("\n--- Testing Push Registration Success ---")

        keys = self._generate_key_pair()
        timestamp = int(time.time() * 1000)  # Current time in milliseconds
        push_endpoint = "fcm:test_token_12345"
        distributor_package = "com.test.distributor"

        signature = generate_push_signature(
            keys["private_key"],
            distributor_package,
            push_endpoint,
            timestamp
        )

        response = requests.post(
            f"{API_URL}/push/register",
            json={
                "push_endpoint": push_endpoint,
                "distributor_package": distributor_package,
                "timestamp": timestamp,
                "client_signature": signature,
                "public_key_pem": keys["public_pem"],
                "key_created_at": "2024-01-01T00:00:00Z"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"

        print("Push registration successful")

    def test_register_push_anonymous(self):
        """Test registering push endpoint without authentication."""
        print("\n--- Testing Push Registration (Anonymous) ---")

        keys = self._generate_key_pair()
        timestamp = int(time.time() * 1000)
        push_endpoint = "fcm:anonymous_token_67890"
        distributor_package = "com.test.distributor"

        signature = generate_push_signature(
            keys["private_key"],
            distributor_package,
            push_endpoint,
            timestamp
        )

        response = requests.post(
            f"{API_URL}/push/register",
            json={
                "push_endpoint": push_endpoint,
                "distributor_package": distributor_package,
                "timestamp": timestamp,
                "client_signature": signature,
                "public_key_pem": keys["public_pem"],
                "key_created_at": "2024-01-01T00:00:00Z"
            }
            # No auth headers - anonymous registration
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"

        print("Anonymous push registration successful")

    def test_register_push_invalid_signature(self):
        """Test push registration with invalid signature."""
        print("\n--- Testing Push Registration (Invalid Signature) ---")

        keys = self._generate_key_pair()
        timestamp = int(time.time() * 1000)

        response = requests.post(
            f"{API_URL}/push/register",
            json={
                "push_endpoint": "fcm:test_token",
                "distributor_package": "com.test.distributor",
                "timestamp": timestamp,
                "client_signature": "invalid_signature_base64",
                "public_key_pem": keys["public_pem"],
                "key_created_at": "2024-01-01T00:00:00Z"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("Invalid signature rejected correctly")

    def test_register_push_expired_timestamp(self):
        """Test push registration with expired timestamp."""
        print("\n--- Testing Push Registration (Expired Timestamp) ---")

        keys = self._generate_key_pair()
        # Timestamp from 10 minutes ago (beyond 5 minute window)
        timestamp = int((time.time() - 600) * 1000)
        push_endpoint = "fcm:expired_test"
        distributor_package = "com.test.distributor"

        signature = generate_push_signature(
            keys["private_key"],
            distributor_package,
            push_endpoint,
            timestamp
        )

        response = requests.post(
            f"{API_URL}/push/register",
            json={
                "push_endpoint": push_endpoint,
                "distributor_package": distributor_package,
                "timestamp": timestamp,
                "client_signature": signature,
                "public_key_pem": keys["public_pem"],
                "key_created_at": "2024-01-01T00:00:00Z"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("Expired timestamp rejected correctly")

    def test_register_push_update_existing(self):
        """Test updating an existing push registration."""
        print("\n--- Testing Push Registration Update ---")

        keys = self._generate_key_pair()
        distributor_package = "com.test.distributor"

        # First registration
        timestamp1 = int(time.time() * 1000)
        push_endpoint1 = "fcm:first_token"
        signature1 = generate_push_signature(
            keys["private_key"],
            distributor_package,
            push_endpoint1,
            timestamp1
        )

        response1 = requests.post(
            f"{API_URL}/push/register",
            json={
                "push_endpoint": push_endpoint1,
                "distributor_package": distributor_package,
                "timestamp": timestamp1,
                "client_signature": signature1,
                "public_key_pem": keys["public_pem"],
                "key_created_at": "2024-01-01T00:00:00Z"
            },
            headers=self.test_headers
        )
        assert response1.status_code == 200, f"First registration failed: {response1.status_code}"
        print("First registration successful")

        # Second registration with same key (update)
        time.sleep(0.1)  # Small delay to ensure different timestamp
        timestamp2 = int(time.time() * 1000)
        push_endpoint2 = "fcm:updated_token"
        signature2 = generate_push_signature(
            keys["private_key"],
            distributor_package,
            push_endpoint2,
            timestamp2
        )

        response2 = requests.post(
            f"{API_URL}/push/register",
            json={
                "push_endpoint": push_endpoint2,
                "distributor_package": distributor_package,
                "timestamp": timestamp2,
                "client_signature": signature2,
                "public_key_pem": keys["public_pem"],
                "key_created_at": "2024-01-01T00:00:00Z"
            },
            headers=self.test_headers
        )

        print(f"Response status: {response2.status_code}")
        print(f"Response: {response2.json()}")

        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}"

        data = response2.json()
        assert "updated" in data.get("message", "").lower(), f"Expected 'updated' in message, got {data}"

        print("Push registration update successful")

    def test_register_push_missing_fields(self):
        """Test push registration with missing required fields."""
        print("\n--- Testing Push Registration (Missing Fields) ---")

        # Missing push_endpoint
        response = requests.post(
            f"{API_URL}/push/register",
            json={
                "distributor_package": "com.test",
                "timestamp": int(time.time() * 1000),
                "client_signature": "test",
                "public_key_pem": "test",
                "key_created_at": "2024-01-01T00:00:00Z"
            },
            headers=self.test_headers
        )
        assert response.status_code == 422, f"Expected 422 for missing push_endpoint, got {response.status_code}"
        print("Missing push_endpoint rejected")

        # Missing client_signature
        response = requests.post(
            f"{API_URL}/push/register",
            json={
                "push_endpoint": "fcm:test",
                "distributor_package": "com.test",
                "timestamp": int(time.time() * 1000),
                "public_key_pem": "test",
                "key_created_at": "2024-01-01T00:00:00Z"
            },
            headers=self.test_headers
        )
        assert response.status_code == 422, f"Expected 422 for missing client_signature, got {response.status_code}"
        print("Missing client_signature rejected")


class TestPushUnregistration(BaseUserManagementTest):
    """Test suite for push unregistration."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        print("Setting up push unregistration tests...")

    def test_unregister_push_requires_auth(self):
        """Test that unregistering requires authentication."""
        print("\n--- Testing Push Unregistration Requires Auth ---")

        response = requests.delete(
            f"{API_URL}/push/unregister/key_test123"
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Authentication required for unregistration")

    def test_unregister_push_not_found(self):
        """Test unregistering a non-existent push registration."""
        print("\n--- Testing Push Unregistration (Not Found) ---")

        response = requests.delete(
            f"{API_URL}/push/unregister/key_nonexistent12345",
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Non-existent registration returns 404")


class TestInternalNotificationEndpoints(BaseUserManagementTest):
    """Test suite for internal notification endpoints."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        print("Setting up internal notification endpoint tests...")

    @pytest.mark.skip(reason="Endpoint temporarily removed")
    def test_internal_create_notification(self):
        """Test creating a notification via internal endpoint."""
        print("\n--- Testing Internal Create Notification ---")

        # Get the test user's ID first
        response = requests.get(
            f"{API_URL}/users/me",
            headers=self.test_headers
        )
        if response.status_code != 200:
            print(f"Could not get user info: {response.status_code}")
            return

        user_id = response.json().get("id")
        print(f"Creating notification for user: {user_id}")

        response = requests.post(
            f"{API_URL}/internal/notifications/create",
            json={
                "user_id": user_id,
                "type": "test",
                "title": "Test Notification",
                "body": "This is a test notification from integration tests"
            }
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert "id" in data, f"Expected 'id' in response, got {data}"

        print(f"Created notification with ID: {data['id']}")

        # Verify the notification appears in the user's list
        response = requests.get(
            f"{API_URL}/notifications/recent",
            headers=self.test_headers
        )
        assert response.status_code == 200
        notifications = response.json()["notifications"]
        assert any(n["title"] == "Test Notification" for n in notifications), \
            "Created notification not found in user's notification list"

        print("Internal notification creation verified")

    @pytest.mark.skip(reason="Endpoint temporarily removed")
    def test_internal_create_notification_missing_target(self):
        """Test internal create notification without user_id or client_key_id."""
        print("\n--- Testing Internal Create Notification (Missing Target) ---")

        response = requests.post(
            f"{API_URL}/internal/notifications/create",
            json={
                "type": "test",
                "title": "Test",
                "body": "Test body"
            }
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("Missing target rejected correctly")

    def test_internal_cleanup_notifications(self):
        """Test cleanup of expired notifications."""
        print("\n--- Testing Internal Cleanup Notifications ---")

        response = requests.post(
            f"{API_URL}/internal/notifications/cleanup"
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"

        print("Notification cleanup successful")

    @pytest.mark.skip(reason="Endpoint temporarily removed")
    def test_internal_broadcast_notification(self):
        """Test broadcast notification."""
        print("\n--- Testing Internal Broadcast Notification ---")

        response = requests.post(
            f"{API_URL}/internal/notifications/broadcast",
            json={
                "type": "announcement",
                "title": "Test Broadcast",
                "body": "This is a test broadcast message"
            }
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert "total" in data, f"Expected 'total' in response, got {data}"

        print(f"Broadcast sent to {data.get('total', 0)} recipients")


class TestNotificationWorkflow(BaseUserManagementTest):
    """Test full notification workflow: create, read, mark as read."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        print("Setting up notification workflow tests...")

    def test_full_notification_workflow(self):
        """Test complete notification lifecycle."""
        print("\n--- Testing Full Notification Workflow ---")

        # Get user ID
        response = requests.get(
            f"{API_URL}/users/me",
            headers=self.test_headers
        )
        if response.status_code != 200:
            print(f"Could not get user info: {response.status_code}")
            return
        user_id = response.json().get("id")

        # Step 1: Create notification
        response = requests.post(
            f"{API_URL}/internal/notifications/create",
            json={
                "user_id": user_id,
                "type": "workflow_test",
                "title": "Workflow Test Notification",
                "body": "Testing the full notification workflow"
            }
        )
        assert response.status_code == 200, f"Failed to create notification: {response.status_code}"
        notification_id = response.json()["id"]
        print(f"Step 1: Created notification ID {notification_id}")

        # Step 2: Check unread count increased
        response = requests.get(
            f"{API_URL}/notifications/unread-count",
            headers=self.test_headers
        )
        assert response.status_code == 200
        unread_before = response.json()["unread_count"]
        print(f"Step 2: Unread count = {unread_before}")
        assert unread_before >= 1, "Expected at least 1 unread notification"

        # Step 3: Get recent notifications and verify it's there
        response = requests.get(
            f"{API_URL}/notifications/recent",
            headers=self.test_headers
        )
        assert response.status_code == 200
        notifications = response.json()["notifications"]
        workflow_notification = next(
            (n for n in notifications if n["id"] == notification_id),
            None
        )
        assert workflow_notification is not None, "Notification not found in recent list"
        assert workflow_notification["read_at"] is None, "New notification should be unread"
        print(f"Step 3: Found notification in recent list (unread)")

        # Step 4: Mark as read
        response = requests.put(
            f"{API_URL}/notifications/read",
            json={"notification_ids": [notification_id]},
            headers=self.test_headers
        )
        assert response.status_code == 200
        print(f"Step 4: Marked notification as read")

        # Step 5: Verify unread count decreased
        response = requests.get(
            f"{API_URL}/notifications/unread-count",
            headers=self.test_headers
        )
        assert response.status_code == 200
        unread_after = response.json()["unread_count"]
        print(f"Step 5: Unread count = {unread_after}")
        assert unread_after == unread_before - 1, \
            f"Expected unread count to decrease by 1, was {unread_before}, now {unread_after}"

        # Step 6: Verify notification is marked as read
        response = requests.get(
            f"{API_URL}/notifications/recent",
            headers=self.test_headers
        )
        assert response.status_code == 200
        notifications = response.json()["notifications"]
        workflow_notification = next(
            (n for n in notifications if n["id"] == notification_id),
            None
        )
        assert workflow_notification is not None
        assert workflow_notification["read_at"] is not None, "Notification should be marked as read"
        print(f"Step 6: Verified notification is now marked as read")

        print("Full notification workflow completed successfully!")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
