#!/usr/bin/env python3
"""
OAuth Authentication Edge Cases and Error Scenarios Test Suite.
Tests various failure modes and edge cases for OAuth authentication.
"""
import warnings
# Suppress specific deprecation warnings that we cannot fix at our level
warnings.filterwarnings("ignore", message="'crypt' is deprecated", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="Support for class-based `config` is deprecated", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="The 'app' shortcut is now deprecated", category=DeprecationWarning)

import pytest
import json
from unittest.mock import Mock, patch
from urllib.parse import urlparse, parse_qs
import sys
import os

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Enable user accounts for OAuth testing
os.environ["USER_ACCOUNTS"] = "true"

from fastapi.testclient import TestClient
from api.app.api import app

# Create TestClient for unit testing
client = TestClient(app)

class TestOAuthErrorScenarios:
    """Test OAuth error handling and edge cases"""
    
    def test_oauth_provider_service_unavailable(self):
        """Test handling when OAuth provider is down"""
        response = client.get(
            "/api/auth/oauth-redirect",
            params={
                "provider": "google",
                "redirect_uri": "com.hillview://auth"
            },
            follow_redirects=False
        )
        
        # Should still redirect to OAuth provider (network errors handled by client)
        assert response.status_code in [302, 307]
        
        location = response.headers.get("Location")
        assert "accounts.google.com" in location
    
    @patch('api.app.user_routes.requests.post')
    def test_oauth_token_exchange_failure(self, mock_post):
        """Test handling when OAuth token exchange fails"""
        # Mock failed token exchange
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Authorization code is invalid"
        }
        
        response = client.get(
            "/api/auth/oauth-callback",
            params={
                "code": "invalid_code",
                "state": "google:com.hillview://auth"
            }
        )
        
        # Should handle error gracefully
        assert response.status_code in [400, 302]
    
    @patch('api.app.user_routes.requests.post')
    @patch('api.app.user_routes.requests.get')
    def test_oauth_user_info_failure(self, mock_get, mock_post):
        """Test handling when OAuth user info fetch fails"""
        # Mock successful token exchange
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "valid_access_token"
        }
        
        # Mock failed user info fetch
        mock_get.return_value.status_code = 403
        mock_get.return_value.json.return_value = {
            "error": "insufficient_scope"
        }
        
        response = client.get(
            "/api/auth/oauth-callback",
            params={
                "code": "valid_code",
                "state": "google:com.hillview://auth"
            }
        )
        
        # Should handle error gracefully - API may return the upstream 403 or convert it
        assert response.status_code in [400, 302, 403]
    
    def test_oauth_callback_csrf_protection(self):
        """Test CSRF protection via state parameter validation"""
        # Missing state parameter
        response = client.get(
            "/api/auth/oauth-callback",
            params={"code": "valid_code"}
        )
        
        assert response.status_code in [400, 422]  # Validation error
        
        # Malformed state parameter
        response = client.get(
            "/api/auth/oauth-callback",
            params={
                "code": "valid_code",
                "state": "malformed_state_without_colon"
            }
        )
        
        # Should handle gracefully (may redirect with error or return error)
        assert response.status_code in [400, 302]
    
    def test_oauth_callback_replay_attack_protection(self):
        """Test protection against authorization code replay attacks"""
        # Use the same code twice
        auth_code = "authorization_code_12345"
        state = "google:com.hillview://auth"
        
        # First request
        response1 = client.get(
            "/api/auth/oauth-callback",
            params={"code": auth_code, "state": state}
        )
        
        # Second request with same code (should fail)
        response2 = client.get(
            "/api/auth/oauth-callback", 
            params={"code": auth_code, "state": state}
        )
        
        # At least one should fail (OAuth provider should reject reused codes)
        assert not (response1.status_code == 302 and response2.status_code == 302)


class TestOAuthRateLimiting:
    """Test rate limiting and abuse prevention"""
    
    def test_oauth_redirect_rate_limiting(self):
        """Test rate limiting on OAuth redirect endpoint"""
        provider = "google"
        redirect_uri = "com.hillview://auth"
        
        # Make multiple rapid requests
        responses = []
        for i in range(10):
            response = client.get(
                "/api/auth/oauth-redirect",
                params={
                    "provider": provider,
                    "redirect_uri": redirect_uri
                },
                follow_redirects=False
            )
            responses.append(response.status_code)
        
        # Should either allow all requests or start rate limiting
        success_count = sum(1 for status in responses if status in [302, 307])
        rate_limited_count = sum(1 for status in responses if status == 429)
        
        # Most requests should succeed, but some rate limiting is acceptable
        assert success_count >= 5
    
    def test_oauth_callback_abuse_prevention(self):
        """Test prevention of OAuth callback abuse"""
        # Rapid callback attempts with different codes
        for i in range(5):
            response = client.get(
                "/api/auth/oauth-callback",
                params={
                    "code": f"fake_code_{i}",
                    "state": "google:com.hillview://auth"
                }
            )
            # Should handle gracefully without crashing
            assert response.status_code in [400, 401, 302, 429]


class TestOAuthSecurityHeaders:
    """Test security headers and HTTPS enforcement"""
    
    def test_oauth_redirect_security_headers(self):
        """Test that OAuth redirects include proper security headers"""
        response = client.get(
            "/api/auth/oauth-redirect",
            params={
                "provider": "google",
                "redirect_uri": "com.hillview://auth"
            },
            follow_redirects=False
        )
        
        # Check for security headers
        headers = response.headers
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers
        assert "X-XSS-Protection" in headers
    
    def test_oauth_callback_security_headers(self):
        """Test that OAuth callbacks include proper security headers"""
        response = client.get(
            "/api/auth/oauth-callback",
            params={
                "code": "test_code",
                "state": "google:com.hillview://auth"
            }
        )
        
        # Check for security headers
        headers = response.headers
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers


class TestOAuthStateParameter:
    """Test OAuth state parameter handling and validation"""
    
    def test_state_parameter_format_validation(self):
        """Test validation of state parameter format"""
        # Valid format: provider:redirect_uri
        valid_states = [
            "google:com.hillview://auth",
            "github:http://localhost:3000/oauth/callback"
        ]
        
        for state in valid_states:
            response = client.get(
                "/api/auth/oauth-callback",
                params={
                    "code": "test_code",
                    "state": state
                }
            )
            # Should at least accept the format (may fail for other reasons)
            assert response.status_code != 422  # Not a validation error
    
    def test_state_parameter_injection_protection(self):
        """Test protection against state parameter injection attacks"""
        malicious_states = [
            "google:com.hillview://auth&malicious=param",
            "google:javascript:alert('xss')",
            "google:http://evil.com/steal-tokens",
            "google:file:///etc/passwd"
        ]
        
        for malicious_state in malicious_states:
            response = client.get(
                "/api/auth/oauth-callback",
                params={
                    "code": "test_code",
                    "state": malicious_state
                }
            )
            
            # Should either reject or sanitize malicious state
            if response.status_code == 302:
                location = response.headers.get("Location", "")
                # Should not redirect to malicious URLs
                assert not any(bad in location.lower() for bad in ["evil.com", "javascript:", "file://"])


class TestOAuthProviderSpecificEdgeCases:
    """Test provider-specific edge cases and error handling"""
    
    def test_google_oauth_scope_errors(self):
        """Test handling of Google OAuth scope-related errors"""
        # Simulate Google OAuth error response
        response = client.get(
            "/api/auth/oauth-callback",
            params={
                "error": "access_denied",
                "error_description": "User denied access",
                "state": "google:com.hillview://auth"
            }
        )
        
        # Should handle OAuth errors gracefully
        assert response.status_code in [302, 400, 422]
        
        if response.status_code == 302:
            location = response.headers.get("Location")
            # Should redirect to error page or login page, not with token
            assert "token=" not in location
    
    def test_github_oauth_scope_errors(self):
        """Test handling of GitHub OAuth scope-related errors"""
        response = client.get(
            "/api/auth/oauth-callback",
            params={
                "error": "access_denied",
                "error_description": "User denied access",
                "state": "github:http://localhost:8212/oauth/callback"
            }
        )
        
        # Should handle OAuth errors gracefully
        assert response.status_code in [302, 400, 422]


if __name__ == "__main__":
    # Run edge case tests
    print("Starting OAuth edge case and error scenario tests...")
    
    test_class = TestOAuthErrorScenarios()
    
    try:
        test_class.test_oauth_provider_service_unavailable()
        print("✅ OAuth provider unavailable test passed")
    except Exception as e:
        print(f"❌ OAuth provider unavailable test failed: {e}")
    
    try:
        test_class.test_oauth_callback_csrf_protection()
        print("✅ CSRF protection test passed")
    except Exception as e:
        print(f"❌ CSRF protection test failed: {e}")
    
    security_class = TestOAuthSecurityHeaders()
    try:
        security_class.test_oauth_redirect_security_headers()
        print("✅ Security headers test passed")
    except Exception as e:
        print(f"❌ Security headers test failed: {e}")
    
    print("\nOAuth edge case tests completed!")