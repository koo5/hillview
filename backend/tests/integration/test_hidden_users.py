#!/usr/bin/env python3
"""
Tests for user hiding endpoints.

Covers:
- POST /api/hidden/users (hide user)
- DELETE /api/hidden/users (unhide user)
- GET /api/hidden/users (list hidden users)
- Authentication and authorization
- Input validation
- Rate limiting
"""

import requests
import json
import time
import os
import sys
from datetime import datetime

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest

# Test configuration
API_URL = os.getenv("API_URL", "http://localhost:8055/api")

class TestUserHiding(BaseUserManagementTest):
    """Test suite for user hiding endpoints."""
    
    def setup_method(self, method=None):
        """Set up test by using parent class setup."""
        super().setup_method(method)
        self.target_user_id = "target_user_456"
        print("Setting up user hiding tests...")
    
    def get_auth_headers(self, token=None):
        """Get authorization headers."""
        # Use provided token or fall back to test token from parent class
        auth_token = token or self.test_token
        return super().get_auth_headers(auth_token)
    
    def test_hide_user_success(self):
        """Test successfully hiding a user."""
        print("\n--- Testing Hide User Success ---")
        
        hide_request = {
            "target_user_source": "hillview",
            "target_user_id": self.target_user_id,
            "reason": "Test user hiding"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        result = response.json()
        assert result.get("success"), f"Expected success=True, got {result}"
        assert "hidden successfully" in result.get("message", ""), f"Expected success message, got {result}"
        
        print("✓ User hidden successfully")
    
    def test_hide_user_duplicate(self):
        """Test hiding a user that's already hidden."""
        print("\n--- Testing Duplicate User Hiding ---")
        
        hide_request = {
            "target_user_source": "hillview",
            "target_user_id": self.target_user_id,
            "reason": "Initial hide for duplicate test"
        }
        
        # First hide the user
        response1 = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_request,
            headers=self.get_auth_headers()
        )
        assert response1.status_code == 200, f"First hide failed: {response1.status_code}"
        print("✓ User hidden initially")
        
        # Now try to hide again (should be duplicate)
        hide_request["reason"] = "Duplicate test"
        response2 = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Duplicate response status: {response2.status_code}")
        print(f"Duplicate response: {response2.json()}")
        
        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}"
        result = response2.json()
        assert result.get("success"), f"Expected success=True, got {result}"
        assert result.get("already_hidden"), f"Expected already_hidden=True, got {result}"
        print("✓ Duplicate hiding handled correctly")
    
    def test_list_hidden_users(self):
        """Test listing hidden users."""
        print("\n--- Testing List Hidden Users ---")
        
        response = requests.get(
            f"{API_URL}/hidden/users",
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            users = response.json()
            print(f"Found {len(users)} hidden users")
            
            # Verify structure
            if users and isinstance(users, list):
                user = users[0]
                required_fields = ["target_user_source", "target_user_id", "hidden_at", "reason"]
                assert all(field in user for field in required_fields), f"Missing required fields in user: {user}"
                print("✓ Hidden users listed successfully")
            elif len(users) == 0:
                print("✓ No hidden users found (valid response)")
            else:
                pytest.fail("Failed to list hidden users")
    
    def test_list_hidden_users_with_filter(self):
        """Test listing hidden users with source filter."""
        print("\n--- Testing List Hidden Users with Filter ---")
        
        # Test filtering by source
        response = requests.get(
            f"{API_URL}/hidden/users?target_user_source=hillview",
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        users = response.json()
        print(f"Found {len(users)} hidden hillview users")
        
        # Verify all results are from hillview source
        for user in users:
            assert user.get("target_user_source") == "hillview", f"Expected hillview source, got {user.get('target_user_source')}"
        
        print("✓ Source filtering working correctly")
    
    def test_unhide_user(self):
        """Test unhiding a user."""
        print("\n--- Testing Unhide User ---")
        
        # First hide the user so we can test unhiding
        hide_request = {
            "target_user_source": "hillview",
            "target_user_id": self.target_user_id,
            "reason": "Setup for unhide test"
        }
        
        hide_response = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_request,
            headers=self.get_auth_headers()
        )
        assert hide_response.status_code == 200, f"Setup hide failed: {hide_response.status_code}"
        print("✓ User hidden for unhide test")
        
        # Now unhide the user
        unhide_request = {
            "target_user_source": "hillview",
            "target_user_id": self.target_user_id
        }
        
        response = requests.delete(
            f"{API_URL}/hidden/users",
            json=unhide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Unhide response status: {response.status_code}")
        print(f"Unhide response: {response.json()}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()
        assert result.get("success"), f"Expected success=True, got {result}"
        assert "unhidden successfully" in result.get("message", ""), f"Expected success message, got {result}"
        print("✓ User unhidden successfully")
    
    def test_unhide_nonexistent_user(self):
        """Test unhiding a user that was never hidden."""
        print("\n--- Testing Unhide Non-existent User ---")
        
        unhide_request = {
            "target_user_source": "hillview",
            "target_user_id": "never_hidden_user_789"
        }
        
        response = requests.delete(
            f"{API_URL}/hidden/users",
            json=unhide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()
        assert result.get("success"), f"Expected success=True, got {result}"
        assert "was not hidden" in result.get("message", ""), f"Expected 'was not hidden' message, got {result}"
        print("✓ Non-existent unhide handled correctly")
    
    def test_authentication_required(self):
        """Test that authentication is required."""
        print("\n--- Testing Authentication Requirements ---")
        
        # Test without auth token
        test_requests = [
            ("POST", {"target_user_source": "hillview", "target_user_id": "test"}),
            ("DELETE", {"target_user_source": "hillview", "target_user_id": "test"}),
            ("GET", None)
        ]
        
        for method, data in test_requests:
            if method == "POST":
                response = requests.post(f"{API_URL}/hidden/users", json=data)
            elif method == "DELETE":
                response = requests.delete(f"{API_URL}/hidden/users", json=data)
            else:  # GET
                response = requests.get(f"{API_URL}/hidden/users")
            
            assert response.status_code == 401, f"{method} should require auth, got {response.status_code}"
        
        print("✓ All endpoints require authentication")
    
    def test_input_validation(self):
        """Test input validation."""
        print("\n--- Testing Input Validation ---")
        
        # Test invalid requests
        invalid_requests = [
            {"target_user_source": "invalid_source", "target_user_id": "test"},
            {"target_user_source": "hillview"},  # Missing target_user_id
            {"target_user_id": "test"},  # Missing target_user_source
            {}  # Empty request
        ]
        
        for invalid_data in invalid_requests:
            response = requests.post(
                f"{API_URL}/hidden/users",
                json=invalid_data,
                headers=self.get_auth_headers()
            )
            
            assert response.status_code in [400, 422], f"Should reject invalid data: {invalid_data}, got {response.status_code}"
        
        # Test invalid source in GET filter
        response = requests.get(
            f"{API_URL}/hidden/users?target_user_source=invalid",
            headers=self.get_auth_headers()
        )
        
        assert response.status_code in [400, 422], f"Should reject invalid source filter, got {response.status_code}"
        
        print("✓ Input validation working correctly")
    
    def run_all_tests(self):
        """Run all user hiding tests."""
        print("=" * 50)
        print("USER HIDING ENDPOINT TESTS")
        print("=" * 50)
        
        if not self.setup_method():
            print("❌ Setup failed!")
            return False
        
        tests = [
            self.test_hide_user_success,
            self.test_hide_user_duplicate,
            self.test_list_hidden_users,
            self.test_list_hidden_users_with_filter,
            self.test_unhide_user,
            self.test_unhide_nonexistent_user,
            self.test_authentication_required,
            self.test_input_validation
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"✗ {test.__name__} failed with exception: {e}")
                failed += 1
        
        print("\n" + "=" * 50)
        print(f"RESULTS: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("🎉 ALL USER HIDING TESTS PASSED!")
            return True
        else:
            print("❌ Some tests failed!")
            return False


def main():
    """Run the user hiding tests."""
    test_runner = TestUserHiding()
    success = test_runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())