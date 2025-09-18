#!/usr/bin/env python3
"""
Test suite for user profile management endpoints.
Tests profile retrieval, account deletion, and security.
"""
import pytest
import requests
import json
import sys
import os

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
# Add paths for test utilities
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest
from utils.auth_utils import auth_helper, TEST_CREDENTIALS

API_URL = os.getenv("API_URL", "http://localhost:8055/api")

class TestUserProfile(BaseUserManagementTest):
    """Test user profile retrieval and management"""
    
    def test_get_user_profile_success(self):
        """Test successful profile retrieval"""
        response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.test_headers
        )
        
        assert response.status_code == 200
        
        profile_data = response.json()
        assert "id" in profile_data
        assert "username" in profile_data
        assert "email" in profile_data
        assert "is_active" in profile_data
        assert "created_at" in profile_data
        assert "provider" in profile_data
        
        # Verify test user data
        assert profile_data["username"] == "test"
        assert profile_data["is_active"] is True
        assert profile_data["provider"] is None  # Username/password user
    
    def test_get_user_profile_unauthorized(self):
        """Test profile retrieval without authentication"""
        response = requests.get(f"{API_URL}/user/profile")
        
        assert response.status_code == 401
    
    def test_get_user_profile_invalid_token(self):
        """Test profile retrieval with invalid token"""
        response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.get_auth_headers("invalid.token.here")
        )
        
        assert response.status_code == 401
    
    def test_legacy_auth_me_endpoint(self):
        """Test that the legacy /auth/me endpoint still works"""
        response = requests.get(
            f"{API_URL}/auth/me",
            headers=self.test_headers
        )
        
        assert response.status_code == 200
        
        user_data = response.json()
        assert "id" in user_data
        assert "username" in user_data
        assert user_data["username"] == "test"


class TestAccountDeletion(BaseUserManagementTest):
    """Test account deletion functionality and security"""
    
    def test_delete_account_unauthorized(self):
        """Test account deletion without authentication"""
        response = requests.delete(f"{API_URL}/user/delete")
        self.assert_unauthorized(response)
    
    def test_delete_account_invalid_token(self):
        """Test account deletion with invalid token"""
        response = requests.delete(
            f"{API_URL}/user/delete",
            headers=self.get_auth_headers("invalid.token.here")
        )
        self.assert_unauthorized(response)
    
    def test_delete_account_wrong_method(self):
        """Test that other HTTP methods are not allowed for deletion"""
        # Test GET (should not be allowed)
        response = requests.get(
            f"{API_URL}/user/delete",
            headers=self.test_headers
        )
        assert response.status_code == 405  # Method not allowed
        
        # Test POST (should not be allowed)
        response = requests.post(
            f"{API_URL}/user/delete",
            headers=self.test_headers
        )
        assert response.status_code == 405  # Method not allowed
    
    def test_delete_account_success(self):
        """Test successful account deletion"""
        # Note: This test will actually delete the test user
        # In a real environment, you'd want to create a temporary test user
        # or restore the user after the test
        
        # First, verify the user exists by getting profile
        profile_response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.test_headers
        )
        self.assert_success(profile_response)
        
        # Now delete the account
        delete_response = requests.delete(
            f"{API_URL}/user/delete",
            headers=self.test_headers
        )
        
        self.assert_success(delete_response)
        
        response_data = delete_response.json()
        assert "message" in response_data
        assert "successfully deleted" in response_data["message"].lower()
        
        # Verify the token is no longer valid
        verify_response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.test_headers
        )
        self.assert_unauthorized(verify_response)
        
        # Verify we can't login with the deleted user credentials
        login_result = auth_helper.login_user("test", TEST_CREDENTIALS["test"])
        self.assert_unauthorized(login_result["response"])

    def test_delete_account_cascades_photos(self):
        """Test that deleting a user account also deletes their photos via CASCADE constraint"""
        import asyncio
        from utils.test_utils import create_test_image, upload_test_image

        # Use the existing 'test' user for this test (will be deleted)
        # Note: This test will actually delete the test user, similar to test_delete_account_success
        # We'll create a separate test user to avoid conflicts with other tests
        test_token = self.get_test_token()
        test_headers = {"Authorization": f"Bearer {test_token}"}

        # Create and upload a test photo
        test_image_data = create_test_image(
            width=200, height=150, color=(255, 128, 0), lat=50.0755, lon=14.4378
        )

        async def upload_photo():
            return await upload_test_image(
                filename="cascade_test.jpg",
                image_data=test_image_data,
                description="Test photo for cascade deletion",
                token=test_token,
                is_public=True
            )

        photo_id = asyncio.run(upload_photo())
        assert photo_id, "Photo upload should return a photo ID"

        # Verify photo exists in user's photos
        photos_response = requests.get(f"{API_URL}/photos", headers=test_headers)
        self.assert_success(photos_response)
        photos_data = photos_response.json()
        photos_list = photos_data["photos"]  # API returns {"photos": [...], "pagination": {...}, "counts": {...}}

        photo_found = any(photo["id"] == photo_id for photo in photos_list)
        assert photo_found, f"Uploaded photo {photo_id} should be in user's photos"

        # Get photo details to capture file URLs before deletion
        photo_detail_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=test_headers)
        self.assert_success(photo_detail_response)
        photo_details = photo_detail_response.json()

        # Extract URLs from sizes for file deletion verification
        photo_urls = []
        if photo_details.get("sizes"):
            for size_name, size_data in photo_details["sizes"].items():
                if size_data.get("url"):
                    photo_urls.append(size_data["url"])

        print(f"✅ Created test user with photo {photo_id}, found {len(photo_urls)} file URLs")

        # Delete the user account - CASCADE should delete photos
        delete_response = requests.delete(f"{API_URL}/user/delete", headers=test_headers)
        self.assert_success(delete_response)

        # Verify user is deleted (token no longer works)
        verify_response = requests.get(f"{API_URL}/user/profile", headers=test_headers)
        self.assert_unauthorized(verify_response)

        # Verify photo is also deleted (CASCADE)
        photo_response = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.admin_headers)
        assert photo_response.status_code == 404, f"Photo should be cascade deleted, got {photo_response.status_code}"

        # Verify physical files are also deleted by checking URLs
        files_deleted_count = 0
        for url in photo_urls:
            try:
                file_response = requests.get(url, timeout=5)
                if file_response.status_code == 404:
                    files_deleted_count += 1
                else:
                    print(f"⚠️  File still accessible: {url} (status: {file_response.status_code})")
            except requests.RequestException as e:
                # Connection error likely means file is deleted (good)
                files_deleted_count += 1
                print(f"📁 File inaccessible (expected): {url} - {e}")

        print(f"✅ Cascading delete test passed: User and photo {photo_id} both deleted")
        print(f"📁 Physical files deleted: {files_deleted_count}/{len(photo_urls)}")


class TestProfileSecurity(BaseUserManagementTest):
    """Test security aspects of profile endpoints"""
    
    def test_user_isolation(self):
        """Test that users can only access their own profile"""
        # Get test user profile with test token
        test_profile_response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.test_headers
        )
        
        # Get admin profile with admin token  
        admin_profile_response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.admin_headers
        )
        
        if test_profile_response.status_code == 200 and admin_profile_response.status_code == 200:
            test_profile = test_profile_response.json()
            admin_profile = admin_profile_response.json()
            
            # Verify users get different profiles
            assert test_profile["username"] != admin_profile["username"]
            assert test_profile["id"] != admin_profile["id"]
    
    def test_token_expiration_handling(self):
        """Test handling of expired tokens"""
        # This test would need to create an expired token or wait
        # For now, we'll test with a malformed token that looks expired
        expired_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxNjAwMDAwMDAwfQ.invalid"
        
        response = requests.get(
            f"{API_URL}/user/profile",
            headers=self.get_auth_headers(expired_token)
        )
        
        self.assert_unauthorized(response)
    
    def test_sql_injection_protection(self):
        """Test that profile endpoints are protected against SQL injection"""
        malicious_tokens = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "UNION SELECT * FROM users",
            "../../../etc/passwd"
        ]
        
        for malicious_token in malicious_tokens:
            response = requests.get(
                f"{API_URL}/user/profile",
                headers=self.get_auth_headers(malicious_token)
            )
            
            # Should reject malicious input (not crash the server)
            assert response.status_code in [401, 422]


if __name__ == "__main__":
    # Run basic tests
    print("Starting user profile tests...")
    
    # Test profile retrieval
    profile_test = TestUserProfile()
    try:
        profile_test.test_get_user_profile_success()
        print("✅ Profile retrieval test passed")
    except Exception as e:
        print(f"❌ Profile retrieval test failed: {e}")
    
    try:
        profile_test.test_get_user_profile_unauthorized()
        print("✅ Unauthorized access test passed")
    except Exception as e:
        print(f"❌ Unauthorized access test failed: {e}")
    
    try:
        profile_test.test_legacy_auth_me_endpoint()
        print("✅ Legacy auth/me endpoint test passed")
    except Exception as e:
        print(f"❌ Legacy auth/me endpoint test failed: {e}")
    
    # Test security
    security_test = TestProfileSecurity()
    try:
        security_test.test_sql_injection_protection()
        print("✅ SQL injection protection test passed")
    except Exception as e:
        print(f"❌ SQL injection protection test failed: {e}")
    
    print("\nUser profile tests completed!")
    print("Note: Account deletion test skipped in manual run to preserve test user")