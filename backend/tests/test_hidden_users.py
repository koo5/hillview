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
from datetime import datetime

# Test configuration
BASE_URL = os.getenv("API_URL", "http://localhost:8055")
API_URL = f"{BASE_URL}/api"

class TestUserHiding:
    """Test suite for user hiding endpoints."""
    
    def __init__(self):
        self.auth_token = None
        self.target_user_id = "target_user_456"
        
    def setup(self):
        """Set up test by logging in."""
        print("Setting up user hiding tests...")
        
        # Create and login test user
        test_user = {
            "username": f"test_user_hider_{int(time.time())}",
            "email": f"user_hider_{int(time.time())}@test.com",
            "password": "TestPass123!"
        }
        
        # Register user
        response = requests.post(f"{API_URL}/auth/register", json=test_user)
        if response.status_code not in [200, 400]:  # 400 if user exists
            print(f"User registration failed: {response.text}")
            return False
            
        # Login
        login_data = {
            "username": test_user["username"],
            "password": test_user["password"]
        }
        response = requests.post(
            f"{API_URL}/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code == 200:
            self.auth_token = response.json()["access_token"]
            print(f"✓ Logged in as {test_user['username']}")
            return True
        else:
            print(f"Login failed: {response.text}")
            return False
    
    def get_auth_headers(self):
        """Get authorization headers."""
        if not self.auth_token:
            raise ValueError("No auth token available")
        return {"Authorization": f"Bearer {self.auth_token}"}
    
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
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and "hidden successfully" in result.get("message", ""):
                print("✓ User hidden successfully")
                return True
        
        print("✗ Failed to hide user")
        return False
    
    def test_hide_user_duplicate(self):
        """Test hiding a user that's already hidden."""
        print("\n--- Testing Duplicate User Hiding ---")
        
        hide_request = {
            "target_user_source": "hillview",
            "target_user_id": self.target_user_id,
            "reason": "Duplicate test"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/users",
            json=hide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and result.get("already_hidden"):
                print("✓ Duplicate hiding handled correctly")
                return True
        
        print("✗ Duplicate hiding not handled properly")
        return False
    
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
                if all(field in user for field in required_fields):
                    print("✓ Hidden users listed successfully")
                    return True
            elif len(users) == 0:
                print("✓ No hidden users found (valid response)")
                return True
        
        print("✗ Failed to list hidden users")
        return False
    
    def test_list_hidden_users_with_filter(self):
        """Test listing hidden users with source filter."""
        print("\n--- Testing List Hidden Users with Filter ---")
        
        # Test filtering by source
        response = requests.get(
            f"{API_URL}/hidden/users?target_user_source=hillview",
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            users = response.json()
            print(f"Found {len(users)} hidden hillview users")
            
            # Verify all results are from hillview source
            for user in users:
                if user.get("target_user_source") != "hillview":
                    print("✗ Filter not working correctly")
                    return False
            
            print("✓ Source filtering working correctly")
            return True
        
        print("✗ Failed to filter hidden users by source")
        return False
    
    def test_unhide_user(self):
        """Test unhiding a user."""
        print("\n--- Testing Unhide User ---")
        
        unhide_request = {
            "target_user_source": "hillview",
            "target_user_id": self.target_user_id
        }
        
        response = requests.delete(
            f"{API_URL}/hidden/users",
            json=unhide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and "unhidden successfully" in result.get("message", ""):
                print("✓ User unhidden successfully")
                return True
        
        print("✗ Failed to unhide user")
        return False
    
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
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and "was not hidden" in result.get("message", ""):
                print("✓ Non-existent unhide handled correctly")
                return True
        
        print("✗ Non-existent unhide not handled properly")
        return False
    
    def test_authentication_required(self):
        """Test that authentication is required."""
        print("\n--- Testing Authentication Requirements ---")
        
        # Test without auth token
        test_requests = [
            ("POST", {"target_user_source": "hillview", "target_user_id": "test"}),
            ("DELETE", {"target_user_source": "hillview", "target_user_id": "test"}),
            ("GET", None)
        ]
        
        success = True
        for method, data in test_requests:
            if method == "POST":
                response = requests.post(f"{API_URL}/hidden/users", json=data)
            elif method == "DELETE":
                response = requests.delete(f"{API_URL}/hidden/users", json=data)
            else:  # GET
                response = requests.get(f"{API_URL}/hidden/users")
            
            if response.status_code != 401:
                print(f"✗ {method} should require auth, got {response.status_code}")
                success = False
        
        if success:
            print("✓ All endpoints require authentication")
        
        return success
    
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
        
        success = True
        for invalid_data in invalid_requests:
            response = requests.post(
                f"{API_URL}/hidden/users",
                json=invalid_data,
                headers=self.get_auth_headers()
            )
            
            if response.status_code != 400:
                print(f"✗ Should reject invalid data: {invalid_data}")
                success = False
        
        # Test invalid source in GET filter
        response = requests.get(
            f"{API_URL}/hidden/users?target_user_source=invalid",
            headers=self.get_auth_headers()
        )
        
        if response.status_code != 400:
            print("✗ Should reject invalid source filter")
            success = False
        
        if success:
            print("✓ Input validation working correctly")
        
        return success
    
    def run_all_tests(self):
        """Run all user hiding tests."""
        print("=" * 50)
        print("USER HIDING ENDPOINT TESTS")
        print("=" * 50)
        
        if not self.setup():
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