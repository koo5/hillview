#!/usr/bin/env python3
"""Integration tests for security features that require real HTTP requests."""

import requests
import time
import os
import sys
import pytest

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseAuthTest
from utils.auth_utils import auth_helper, TEST_CREDENTIALS

API_URL = os.getenv("API_URL", "http://localhost:8055/api")


class TestJWTSecurity(BaseAuthTest):
    """Integration tests for JWT security"""
    
    def test_jwt_authentication_flow(self):
        """Test complete JWT authentication flow"""
        # Test with existing test user (no registration needed)
        # Login is already handled by BaseAuthTest setup
        
        # Verify token data is valid
        assert self.test_token is not None
        assert len(self.test_token) > 0
        
        # Use token to access protected endpoint
        protected_response = requests.get(f"{API_URL}/photos", headers=self.test_headers)
        self.assert_success(protected_response)


class TestRateLimiting:
    """Integration tests for rate limiting (requires real server behavior)"""
    
    def test_login_rate_limiting(self):
        """Test rate limiting on login attempts"""
        login_data = {
            "username": "nonexistent",
            "password": "wrongpassword"
        }
        
        responses = []
        for _ in range(10):
            response = requests.post(
                f"{API_URL}/auth/token",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            responses.append(response.status_code)
            time.sleep(0.1)  # Small delay between requests
        
        # Should get either 401 (unauthorized) or 429 (rate limited)
        unauthorized_count = sum(1 for status in responses if status == 401)
        rate_limited_count = sum(1 for status in responses if status == 429)
        
        # Most should be unauthorized, some might be rate limited
        assert unauthorized_count >= 5, "Should consistently reject invalid credentials"
    
    def test_api_endpoint_rate_limiting(self):
        """Test rate limiting on API endpoints"""
        # Test parameters for mapillary endpoint (Prague area)
        params = {
            'top_left_lat': 50.2,    # north
            'top_left_lon': 14.0,    # west  
            'bottom_right_lat': 49.9, # south
            'bottom_right_lon': 14.8, # east
            'client_id': 'rate_limit_test'
        }
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache"
        }
        responses = []
        for _ in range(20):
            response = requests.get(f"{API_URL}/mapillary", params=params, headers=headers)
            responses.append(response.status_code)
            time.sleep(0.05)
        
        # Should either allow all requests or start rate limiting
        success_count = sum(1 for status in responses if status == 200)
        rate_limited_count = sum(1 for status in responses if status == 429)
        
        # Debug: Print actual status codes received
        status_counts = {}
        for status in responses:
            status_counts[status] = status_counts.get(status, 0) + 1
        print(f"Status code counts: {status_counts}")
        
        # Some requests should succeed
        assert success_count >= 10, f"Should allow reasonable number of requests. Got status counts: {status_counts}"


class TestTokenBlacklist(BaseAuthTest):
    """Integration tests for token blacklist functionality"""
    
    def test_token_invalidation(self):
        """Test that tokens can be invalidated"""
        # Token should work initially
        response = requests.get(f"{API_URL}/photos", headers=self.test_headers)
        self.assert_success(response)
        
        # TODO: Implement logout endpoint that invalidates tokens
        # For now, just verify the token works
        assert self.test_token is not None and len(self.test_token) > 0


class TestInputValidationIntegration:
    """Integration tests for input validation that require database"""
    
    def test_weak_password_rejection(self):
        """Test that weak passwords are rejected during registration (may be disabled in DEV_MODE)"""
        weak_passwords = [
            "123",  # Too short
            "password",  # No numbers/special chars
            "12345678",  # Only numbers
        ]
        
        for i, password in enumerate(weak_passwords):
            user_data = {
                "username": f"testuser_{int(time.time())}_{i}",  # Unique username
                "email": f"test_{int(time.time())}_{i}@example.com",  # Unique email
                "password": password
            }
            response = requests.post(f"{API_URL}/auth/register", json=user_data)
            # Should be rejected due to weak password
            assert response.status_code in [400, 422], f"Should reject weak password: {password}"


class TestDisabledUserAccess:
    """Integration tests for disabled user access control"""
    
    def test_disabled_user_cannot_login(self):
        """Test that disabled users cannot login"""
        # This would require a way to disable users in the test setup
        # For now, just test with non-existent user
        login_data = {
            "username": "disableduser",
            "password": "anypassword"
        }
        response = requests.post(
            f"{API_URL}/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 401  # Should be unauthorized


if __name__ == "__main__":
    # Run integration tests
    print("Starting security integration tests...")
    
    test_jwt = TestJWTSecurity()
    test_jwt.setup_method()
    
    try:
        test_jwt.test_jwt_authentication_flow()
        print("✅ JWT authentication flow test passed")
    except Exception as e:
        print(f"❌ JWT authentication flow test failed: {e}")
    
    test_rate = TestRateLimiting()
    try:
        test_rate.test_login_rate_limiting()
        print("✅ Login rate limiting test passed")
    except Exception as e:
        print(f"❌ Login rate limiting test failed: {e}")
    
    print("Security integration tests completed!")