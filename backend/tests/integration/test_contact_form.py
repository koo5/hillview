#!/usr/bin/env python3
"""
Tests for contact form endpoints.

Covers:
- POST /api/contact (submit contact message)
- GET /api/admin/contact/messages (admin only)
- Authentication (logged in vs anonymous)
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


class TestContactForm(BaseUserManagementTest):
    """Test suite for contact form endpoints."""

    def setup_method(self, method=None):
        """Set up test."""
        super().setup_method(method)
        print("Setting up contact form tests...")

    def test_submit_contact_authenticated(self):
        """Test submitting contact message as authenticated user."""
        print("\n--- Testing Contact Submit (Authenticated) ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "test@example.com",
                "message": "This is a test message from an authenticated user."
            },
            headers=self.test_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert "id" in data, f"Expected id in response, got {data}"
        assert data["id"] is not None, f"Expected non-null id, got {data}"

        print("✓ Contact message submitted successfully (authenticated)")

    def test_submit_contact_anonymous(self):
        """Test submitting contact message as anonymous user."""
        print("\n--- Testing Contact Submit (Anonymous) ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "anonymous@example.com",
                "message": "This is a test message from an anonymous user."
            }
            # No auth headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert "id" in data, f"Expected id in response, got {data}"

        print("✓ Contact message submitted successfully (anonymous)")

    def test_validation_contact_too_short(self):
        """Test validation: contact info too short."""
        print("\n--- Testing Validation (Contact Too Short) ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "ab",  # Less than 3 chars
                "message": "This is a valid message with enough characters."
            }
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✓ Correctly rejected contact too short")

    def test_validation_contact_too_long(self):
        """Test validation: contact info too long."""
        print("\n--- Testing Validation (Contact Too Long) ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "x" * 501,  # More than 500 chars
                "message": "This is a valid message with enough characters."
            }
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✓ Correctly rejected contact too long")

    def test_validation_message_too_short(self):
        """Test validation: message too short."""
        print("\n--- Testing Validation (Message Too Short) ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "valid@example.com",
                "message": "Too short"  # Less than 10 chars
            }
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✓ Correctly rejected message too short")

    def test_validation_message_too_long(self):
        """Test validation: message too long."""
        print("\n--- Testing Validation (Message Too Long) ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "valid@example.com",
                "message": "x" * 5001  # More than 5000 chars
            }
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✓ Correctly rejected message too long")

    def test_validation_missing_fields(self):
        """Test validation: missing required fields."""
        print("\n--- Testing Validation (Missing Fields) ---")

        # Missing message
        response = requests.post(
            f"{API_URL}/contact",
            json={"contact": "test@example.com"}
        )
        assert response.status_code == 422, f"Expected 422 for missing message, got {response.status_code}"
        print("✓ Correctly rejected missing message")

        # Missing contact
        response = requests.post(
            f"{API_URL}/contact",
            json={"message": "This is a valid message with enough characters."}
        )
        assert response.status_code == 422, f"Expected 422 for missing contact, got {response.status_code}"
        print("✓ Correctly rejected missing contact")

        # Empty body
        response = requests.post(
            f"{API_URL}/contact",
            json={}
        )
        assert response.status_code == 422, f"Expected 422 for empty body, got {response.status_code}"
        print("✓ Correctly rejected empty body")

    def test_admin_messages_requires_admin(self):
        """Test admin endpoint rejects non-admin users."""
        print("\n--- Testing Admin Messages (Non-Admin) ---")

        response = requests.get(
            f"{API_URL}/admin/contact/messages",
            headers=self.test_headers  # Regular user, not admin
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Correctly rejected non-admin user")

    def test_admin_messages_requires_auth(self):
        """Test admin endpoint rejects unauthenticated requests."""
        print("\n--- Testing Admin Messages (No Auth) ---")

        response = requests.get(f"{API_URL}/admin/contact/messages")

        print(f"Response status: {response.status_code}")

        assert response.status_code in [401, 403], f"Expected 401 or 403, got {response.status_code}"
        print("✓ Correctly rejected unauthenticated request")

    def test_admin_messages_success(self):
        """Test admin can view contact messages."""
        print("\n--- Testing Admin Messages (Success) ---")

        # First submit a message so there's something to retrieve
        requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "admin-test@example.com",
                "message": "Test message for admin retrieval test."
            }
        )

        # Get messages as admin
        response = requests.get(
            f"{API_URL}/admin/contact/messages",
            headers=self.admin_headers
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert "messages" in data, f"Expected 'messages' in response, got {data}"
        assert "total" in data, f"Expected 'total' in response, got {data}"
        assert isinstance(data["messages"], list), f"Expected messages to be a list, got {type(data['messages'])}"

        print(f"✓ Admin retrieved {data['total']} contact messages")

    def test_whitespace_trimming(self):
        """Test that whitespace is properly trimmed from inputs."""
        print("\n--- Testing Whitespace Trimming ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "   test@example.com   ",
                "message": "   This message has leading and trailing whitespace.   "
            }
        )

        print(f"Response status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Whitespace trimming handled correctly")

    def test_unicode_content(self):
        """Test handling of unicode content."""
        print("\n--- Testing Unicode Content ---")

        response = requests.post(
            f"{API_URL}/contact",
            json={
                "contact": "用户@example.com",
                "message": "Zpráva s českými znaky: ěščřžýáíé 日本語テスト"
            }
        )

        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Unicode content handled correctly")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
