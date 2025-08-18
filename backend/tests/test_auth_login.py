#!/usr/bin/env python3
"""
Test suite for username/password authentication with test users.
Tests the complete login flow including token validation and user roles.
"""
import pytest
import requests
import json
import sys
import os

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = "http://localhost:8055"

class TestUserPasswordAuth:
    """Test username/password authentication flow"""
    
    def test_valid_user_login(self):
        """Test successful login with test user credentials"""
        login_data = {
            "username": "test",
            "password": "test123"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 200, f"Login failed with status {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "access_token" in response_data
        assert "token_type" in response_data
        assert response_data["token_type"] == "bearer"
        
        # Verify token format (should be a JWT)
        token = response_data["access_token"]
        token_parts = token.split('.')
        assert len(token_parts) == 3, f"Invalid JWT format: {token}"
        
        # Verify each JWT part is not empty
        for part in token_parts:
            assert len(part) > 0, "JWT part cannot be empty"
    
    def test_valid_admin_login(self):
        """Test successful login with admin user credentials"""
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
        
        response_data = response.json()
        assert "access_token" in response_data
        assert "token_type" in response_data
        assert response_data["token_type"] == "bearer"
    
    def test_invalid_username(self):
        """Test login with invalid username"""
        login_data = {
            "username": "nonexistent_user",
            "password": "test123"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 401
        
        response_data = response.json()
        assert "detail" in response_data
        assert "Incorrect username or password" in response_data["detail"]
    
    def test_invalid_password(self):
        """Test login with valid username but wrong password"""
        login_data = {
            "username": "test",
            "password": "wrong_password"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 401
        
        response_data = response.json()
        assert "detail" in response_data
        assert "Incorrect username or password" in response_data["detail"]
    
    def test_empty_credentials(self):
        """Test login with empty username/password"""
        empty_credentials = [
            {"username": "", "password": "test123"},
            {"username": "test", "password": ""},
            {"username": "", "password": ""}
        ]
        
        for credentials in empty_credentials:
            response = requests.post(
                f"{BASE_URL}/api/auth/token",
                data=credentials,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            # Should reject empty credentials
            assert response.status_code in [401, 422], f"Empty credentials should be rejected: {credentials}"
    
    def test_missing_form_fields(self):
        """Test login with missing form fields"""
        # Missing password
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data={"username": "test"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 422  # FastAPI validation error
        
        # Missing username
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data={"password": "test123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 422  # FastAPI validation error
    
    def test_wrong_content_type(self):
        """Test login with wrong content type (JSON instead of form data)"""
        login_data = {
            "username": "test",
            "password": "test123"
        }
        
        # Try sending as JSON instead of form data
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            json=login_data
        )
        
        # Should reject wrong content type
        assert response.status_code == 422


class TestTokenValidation:
    """Test JWT token validation and usage"""
    
    def get_valid_token(self):
        """Helper to get a valid token for testing"""
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
    
    def test_protected_endpoint_with_valid_token(self):
        """Test accessing protected endpoint with valid token"""
        token = self.get_valid_token()
        
        # Try accessing a protected endpoint (assuming photos endpoint requires auth)
        response = requests.get(
            f"{BASE_URL}/api/photos",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should succeed or return 404 if no photos, but not 401 unauthorized
        assert response.status_code != 401, "Valid token should not result in unauthorized"
    
    def test_protected_endpoint_without_token(self):
        """Test accessing protected endpoint without token"""
        response = requests.get(f"{BASE_URL}/api/photos")
        
        # Should either succeed with limited data or require authentication
        # The exact behavior depends on the endpoint implementation
        assert response.status_code in [200, 401], "Endpoint should handle missing auth gracefully"
    
    def test_protected_endpoint_with_invalid_token(self):
        """Test accessing protected endpoint with invalid token"""
        invalid_tokens = [
            "invalid.token.here",
            "Bearer invalid_token",
            "not.a.jwt",
            ""
        ]
        
        for invalid_token in invalid_tokens:
            response = requests.get(
                f"{BASE_URL}/api/photos",
                headers={"Authorization": f"Bearer {invalid_token}"}
            )
            
            # Should handle invalid tokens gracefully
            assert response.status_code in [401, 422], f"Invalid token should be rejected: {invalid_token}"
    
    def test_token_format_validation(self):
        """Test that returned tokens have correct format"""
        token = self.get_valid_token()
        
        # JWT should have 3 parts separated by dots
        parts = token.split('.')
        assert len(parts) == 3, f"JWT should have 3 parts, got {len(parts)}"
        
        # Each part should be base64-encoded (basic check - should not be empty)
        for i, part in enumerate(parts):
            assert len(part) > 0, f"JWT part {i} should not be empty"
            # Basic base64 character check
            import re
            assert re.match(r'^[A-Za-z0-9_-]+$', part), f"JWT part {i} contains invalid characters"


class TestUserRoles:
    """Test user role functionality"""
    
    def get_user_token(self):
        """Get token for regular user"""
        login_data = {"username": "test", "password": "test123"}
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def get_admin_token(self):
        """Get token for admin user"""
        login_data = {"username": "admin", "password": "admin123"}
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_user_token_properties(self):
        """Test that user and admin tokens have expected properties"""
        user_token = self.get_user_token()
        admin_token = self.get_admin_token()
        
        # Both should be valid JWT tokens
        for token in [user_token, admin_token]:
            parts = token.split('.')
            assert len(parts) == 3, "Token should be valid JWT"
            
        # Tokens should be different
        assert user_token != admin_token, "User and admin tokens should be different"
    
    def test_admin_vs_user_access(self):
        """Test that admin and user tokens work for basic operations"""
        user_token = self.get_user_token()
        admin_token = self.get_admin_token()
        
        # Both should be able to access basic endpoints
        for token in [user_token, admin_token]:
            response = requests.get(
                f"{BASE_URL}/api/photos",
                headers={"Authorization": f"Bearer {token}"}
            )
            # Should not get unauthorized
            assert response.status_code != 401, "Valid tokens should not be unauthorized"


class TestLoginSecurity:
    """Test security aspects of login system"""
    
    def test_password_case_sensitivity(self):
        """Test that passwords are case sensitive"""
        # Test with wrong case
        login_data = {
            "username": "test",
            "password": "TEST123"  # Wrong case
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 401, "Passwords should be case sensitive"
    
    def test_username_case_handling(self):
        """Test username case handling"""
        # Try with different cases
        usernames_to_test = ["TEST", "Test", "tEsT"]
        
        for username in usernames_to_test:
            login_data = {
                "username": username,
                "password": "test123"
            }
            
            response = requests.post(
                f"{BASE_URL}/api/auth/token",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            # Depending on implementation, this might succeed or fail
            # Document the behavior
            if response.status_code == 200:
                print(f"✓ Username '{username}' accepted (case insensitive)")
            else:
                print(f"✗ Username '{username}' rejected (case sensitive)")
    
    def test_sql_injection_attempts(self):
        """Test basic SQL injection protection"""
        malicious_inputs = [
            "test'; DROP TABLE users; --",
            "test' OR '1'='1",
            "test' UNION SELECT * FROM users --",
            "admin'--",
            "' OR 1=1 --"
        ]
        
        for malicious_input in malicious_inputs:
            login_data = {
                "username": malicious_input,
                "password": "test123"
            }
            
            response = requests.post(
                f"{BASE_URL}/api/auth/token",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            # Should reject malicious input (not crash the server)
            assert response.status_code in [401, 422], f"SQL injection attempt should be rejected: {malicious_input}"
    
    def test_rate_limiting_protection(self):
        """Test basic rate limiting on login attempts"""
        login_data = {
            "username": "test",
            "password": "wrong_password"
        }
        
        # Make multiple failed login attempts
        responses = []
        for i in range(10):
            response = requests.post(
                f"{BASE_URL}/api/auth/token",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            responses.append(response.status_code)
        
        # Should consistently return 401 or start rate limiting
        unauthorized_count = sum(1 for status in responses if status == 401)
        rate_limited_count = sum(1 for status in responses if status == 429)
        
        # Most should be unauthorized, some might be rate limited
        assert unauthorized_count >= 5, "Multiple failed attempts should be consistently handled"
        
        if rate_limited_count > 0:
            print(f"✓ Rate limiting detected: {rate_limited_count} requests blocked")
        else:
            print("ℹ No rate limiting detected (may not be implemented)")


if __name__ == "__main__":
    # Run basic tests
    print("Starting username/password authentication tests...")
    
    # Test basic login
    test_class = TestUserPasswordAuth()
    try:
        test_class.test_valid_user_login()
        print("✅ Valid user login test passed")
    except Exception as e:
        print(f"❌ Valid user login test failed: {e}")
    
    try:
        test_class.test_valid_admin_login()
        print("✅ Valid admin login test passed")
    except Exception as e:
        print(f"❌ Valid admin login test failed: {e}")
    
    try:
        test_class.test_invalid_username()
        print("✅ Invalid username test passed")
    except Exception as e:
        print(f"❌ Invalid username test failed: {e}")
    
    try:
        test_class.test_invalid_password()
        print("✅ Invalid password test passed")
    except Exception as e:
        print(f"❌ Invalid password test failed: {e}")
    
    # Test token validation
    token_class = TestTokenValidation()
    try:
        token_class.test_token_format_validation()
        print("✅ Token format validation test passed")
    except Exception as e:
        print(f"❌ Token format validation test failed: {e}")
    
    print("\nUsername/password authentication tests completed!")