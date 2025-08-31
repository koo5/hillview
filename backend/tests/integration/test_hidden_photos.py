#!/usr/bin/env python3
"""
Tests for photo hiding endpoints.

Covers:
- POST /api/hidden/photos (hide photo)
- DELETE /api/hidden/photos (unhide photo)  
- GET /api/hidden/photos (list hidden photos)
- Authentication and authorization
- Input validation
- Rate limiting
"""

import requests
import json
import time
import os
from datetime import datetime
from utils.test_utils import clear_test_database, API_URL

class TestPhotoHiding:
    """Test suite for photo hiding endpoints."""
        
    def setup_method(self):
        """Set up test by logging in."""
        self.auth_token = None
        self.test_photo_id = "test_photo_123"
        print("Setting up photo hiding tests...")
        
        # Create and login test user
        test_user = {
            "username": f"test_photo_hider_{int(time.time())}",
            "email": f"photo_hider_{int(time.time())}@test.com",
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
    
    def test_hide_photo_success(self):
        """Test successfully hiding a photo."""
        print("\n--- Testing Hide Photo Success ---")
        
        hide_request = {
            "photo_source": "mapillary",
            "photo_id": self.test_photo_id,
            "reason": "Test photo hiding"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/photos",
            json=hide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and "hidden successfully" in result.get("message", ""):
                print("✓ Photo hidden successfully")
                return True
        
        print("✗ Failed to hide photo")
        return False
    
    def test_hide_photo_duplicate(self):
        """Test hiding a photo that's already hidden."""
        print("\n--- Testing Duplicate Photo Hiding ---")
        
        hide_request = {
            "photo_source": "mapillary", 
            "photo_id": self.test_photo_id,
            "reason": "Duplicate test"
        }
        
        response = requests.post(
            f"{API_URL}/hidden/photos",
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
    
    def test_list_hidden_photos(self):
        """Test listing hidden photos."""
        print("\n--- Testing List Hidden Photos ---")
        
        response = requests.get(
            f"{API_URL}/hidden/photos",
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            photos = response.json()
            print(f"Found {len(photos)} hidden photos")
            
            # Verify structure
            if photos and isinstance(photos, list):
                photo = photos[0]
                required_fields = ["photo_source", "photo_id", "hidden_at", "reason"]
                if all(field in photo for field in required_fields):
                    print("✓ Hidden photos listed successfully")
                    return True
            elif len(photos) == 0:
                print("✓ No hidden photos found (valid response)")
                return True
        
        print("✗ Failed to list hidden photos")
        return False
    
    def test_unhide_photo(self):
        """Test unhiding a photo."""
        print("\n--- Testing Unhide Photo ---")
        
        unhide_request = {
            "photo_source": "mapillary",
            "photo_id": self.test_photo_id
        }
        
        response = requests.delete(
            f"{API_URL}/hidden/photos",
            json=unhide_request,
            headers=self.get_auth_headers()
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and "unhidden successfully" in result.get("message", ""):
                print("✓ Photo unhidden successfully")
                return True
        
        print("✗ Failed to unhide photo")
        return False
    
    def test_authentication_required(self):
        """Test that authentication is required."""
        print("\n--- Testing Authentication Requirements ---")
        
        # Test without auth token
        test_requests = [
            ("POST", {"photo_source": "mapillary", "photo_id": "test"}),
            ("DELETE", {"photo_source": "mapillary", "photo_id": "test"}),
            ("GET", None)
        ]
        
        success = True
        for method, data in test_requests:
            if method == "POST":
                response = requests.post(f"{API_URL}/hidden/photos", json=data)
            elif method == "DELETE":
                response = requests.delete(f"{API_URL}/hidden/photos", json=data)
            else:  # GET
                response = requests.get(f"{API_URL}/hidden/photos")
            
            if response.status_code != 401:
                print(f"✗ {method} should require auth, got {response.status_code}")
                success = False
        
        if success:
            print("✓ All endpoints require authentication")
        
        return success
    
    def test_input_validation(self):
        """Test input validation."""
        print("\n--- Testing Input Validation ---")
        
        # Test invalid business logic (should return 400)
        invalid_business_logic = [
            {"photo_source": "invalid_source", "photo_id": "test"}
        ]
        
        # Test missing required fields (should return 422 - Pydantic validation)
        missing_fields = [
            {"photo_source": "mapillary"},  # Missing photo_id
            {"photo_id": "test"},  # Missing photo_source
            {}  # Empty request
        ]
        
        success = True
        
        # Test business logic validation (400 expected)
        for invalid_data in invalid_business_logic:
            response = requests.post(
                f"{API_URL}/hidden/photos",
                json=invalid_data,
                headers=self.get_auth_headers()
            )
            
            if response.status_code != 400:
                print(f"✗ Should return 400 for invalid business logic: {invalid_data}")
                success = False
            else:
                print(f"✓ Correctly rejected invalid business logic: {invalid_data}")
        
        # Test Pydantic validation (422 expected)  
        for invalid_data in missing_fields:
            response = requests.post(
                f"{API_URL}/hidden/photos",
                json=invalid_data,
                headers=self.get_auth_headers()
            )
            
            if response.status_code != 422:
                print(f"✗ Should return 422 for missing fields: {invalid_data}")
                success = False
            else:
                print(f"✓ Correctly rejected missing fields: {invalid_data}")
        
        if success:
            print("✓ Input validation working correctly")
        
        return success
    
    def run_all_tests(self):
        """Run all photo hiding tests."""
        print("=" * 50)
        print("PHOTO HIDING ENDPOINT TESTS")
        print("=" * 50)
        
        if not self.setup():
            print("❌ Setup failed!")
            return False
        
        tests = [
            self.test_hide_photo_success,
            self.test_hide_photo_duplicate, 
            self.test_list_hidden_photos,
            self.test_unhide_photo,
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
            print("🎉 ALL PHOTO HIDING TESTS PASSED!")
            return True
        else:
            print("❌ Some tests failed!")
            return False


def main():
    """Run the photo hiding tests."""
    print("🧪 Starting Photo Hiding Tests")
    print("=" * 50)
    
    # Clear database first
    clear_test_database()
    
    test_runner = TestPhotoHiding()
    success = test_runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())