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
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = "http://localhost:8055"

class TestUserProfile:
    """Test user profile retrieval and management"""
    
    def get_test_user_token(self):
        """Helper to get a valid token for test user"""
        login_data = {
            "username": "test",
            "password": "test123"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def get_admin_token(self):
        """Helper to get a valid token for admin user"""
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_get_user_profile_success(self):
        """Test successful profile retrieval"""
        token = self.get_test_user_token()
        
        response = requests.get(
            f"{BASE_URL}/api/user/profile",
            headers={"Authorization": f"Bearer {token}"}
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
        response = requests.get(f"{BASE_URL}/api/user/profile")
        
        assert response.status_code == 401
    
    def test_get_user_profile_invalid_token(self):
        """Test profile retrieval with invalid token"""
        response = requests.get(
            f"{BASE_URL}/api/user/profile",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        
        assert response.status_code == 401
    
    def test_legacy_auth_me_endpoint(self):
        """Test that the legacy /auth/me endpoint still works"""
        token = self.get_test_user_token()
        
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        
        user_data = response.json()
        assert "id" in user_data
        assert "username" in user_data
        assert user_data["username"] == "test"


class TestAccountDeletion:
    """Test account deletion functionality and security"""
    
    def test_delete_account_unauthorized(self):
        """Test account deletion without authentication"""
        response = requests.delete(f"{BASE_URL}/api/user/delete")
        
        assert response.status_code == 401
    
    def test_delete_account_invalid_token(self):
        """Test account deletion with invalid token"""
        response = requests.delete(
            f"{BASE_URL}/api/user/delete",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        
        assert response.status_code == 401
    
    def test_delete_account_wrong_method(self):
        """Test that other HTTP methods are not allowed for deletion"""
        token = self.get_test_user_token()
        
        # Test GET (should not be allowed)
        response = requests.get(
            f"{BASE_URL}/api/user/delete",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 405  # Method not allowed
        
        # Test POST (should not be allowed)
        response = requests.post(
            f"{BASE_URL}/api/user/delete",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 405  # Method not allowed
    
    def get_test_user_token(self):
        """Helper to get a valid token for test user"""
        login_data = {
            "username": "test",
            "password": "test123"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_delete_account_success(self):
        """Test successful account deletion"""
        # Note: This test will actually delete the test user
        # In a real environment, you'd want to create a temporary test user
        # or restore the user after the test
        
        # First, verify the user exists by getting profile
        token = self.get_test_user_token()
        
        profile_response = requests.get(
            f"{BASE_URL}/api/user/profile",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert profile_response.status_code == 200
        
        # Now delete the account
        delete_response = requests.delete(
            f"{BASE_URL}/api/user/delete",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert delete_response.status_code == 200
        
        response_data = delete_response.json()
        assert "message" in response_data
        assert "successfully deleted" in response_data["message"].lower()
        
        # Verify the token is no longer valid
        verify_response = requests.get(
            f"{BASE_URL}/api/user/profile",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert verify_response.status_code == 401
        
        # Verify we can't login with the deleted user credentials
        login_response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data={"username": "test", "password": "test123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert login_response.status_code == 401


class TestProfileSecurity:
    """Test security aspects of profile endpoints"""
    
    def get_tokens_for_different_users(self):
        """Helper to get tokens for different users"""
        # Get test user token
        test_login = requests.post(
            f"{BASE_URL}/api/auth/token",
            data={"username": "test", "password": "test123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        admin_login = requests.post(
            f"{BASE_URL}/api/auth/token",
            data={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        test_token = None
        admin_token = None
        
        if test_login.status_code == 200:
            test_token = test_login.json()["access_token"]
        
        if admin_login.status_code == 200:
            admin_token = admin_login.json()["access_token"]
            
        return test_token, admin_token
    
    def test_user_isolation(self):
        """Test that users can only access their own profile"""
        test_token, admin_token = self.get_tokens_for_different_users()
        
        # Skip if we don't have both users (e.g., test user was deleted)
        if not test_token or not admin_token:
            pytest.skip("Both test users not available")
        
        # Get test user profile with test token
        test_profile_response = requests.get(
            f"{BASE_URL}/api/user/profile",
            headers={"Authorization": f"Bearer {test_token}"}
        )
        
        # Get admin profile with admin token  
        admin_profile_response = requests.get(
            f"{BASE_URL}/api/user/profile",
            headers={"Authorization": f"Bearer {admin_token}"}
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
            f"{BASE_URL}/api/user/profile",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == 401
    
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
                f"{BASE_URL}/api/user/profile",
                headers={"Authorization": f"Bearer {malicious_token}"}
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