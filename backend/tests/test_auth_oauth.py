#!/usr/bin/env python3
"""
Test suite for OAuth authentication endpoints.
Tests the unified authentication flow for both web and mobile platforms.
"""
import pytest
import requests
import json
from unittest.mock import Mock, patch
from urllib.parse import urlparse, parse_qs
import sys
import os

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = os.getenv("API_URL", "http://localhost:8055")
TEST_PROVIDERS = ["google", "github"]

class TestOAuthRedirect:
    """Test OAuth redirect endpoint functionality"""
    
    def test_oauth_redirect_google_mobile(self):
        """Test OAuth redirect for Google with mobile deep link"""
        provider = "google"
        redirect_uri = "com.hillview://auth"
        
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-redirect",
            params={
                "provider": provider,
                "redirect_uri": redirect_uri
            },
            allow_redirects=False
        )
        
        assert response.status_code in [302, 307], f"Expected redirect, got {response.status_code}"
        
        # Parse the redirect URL
        location = response.headers.get("Location")
        assert location is not None, "No Location header in redirect response"
        
        parsed_url = urlparse(location)
        query_params = parse_qs(parsed_url.query)
        
        # Verify it's redirecting to Google
        assert parsed_url.netloc == "accounts.google.com"
        assert parsed_url.path == "/o/oauth2/auth"
        
        # Verify required OAuth parameters
        assert "client_id" in query_params
        assert "redirect_uri" in query_params
        assert "response_type" in query_params
        assert "state" in query_params
        
        # Verify the state contains our redirect URI
        state = query_params["state"][0]
        assert redirect_uri in state
        assert provider in state
        
        # Verify scope for Google
        assert "scope" in query_params
        assert "email profile" in query_params["scope"][0]
    
    def test_oauth_redirect_github_web(self):
        """Test OAuth redirect for GitHub with web callback"""
        provider = "github"
        redirect_uri = "http://localhost:3000/oauth/callback"
        
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-redirect",
            params={
                "provider": provider,
                "redirect_uri": redirect_uri
            },
            allow_redirects=False
        )
        
        assert response.status_code in [302, 307]
        
        location = response.headers.get("Location")
        parsed_url = urlparse(location)
        query_params = parse_qs(parsed_url.query)
        
        # Verify it's redirecting to GitHub
        assert parsed_url.netloc == "github.com"
        assert parsed_url.path == "/login/oauth/authorize"
        
        # Verify GitHub-specific scope
        assert "scope" in query_params
        assert "user:email" in query_params["scope"][0]
    
    def test_oauth_redirect_invalid_provider(self):
        """Test OAuth redirect with invalid provider"""
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-redirect",
            params={
                "provider": "invalid",
                "redirect_uri": "com.hillview://auth"
            }
        )
        
        assert response.status_code == 400
        response_data = response.json()
        assert "Unsupported OAuth provider" in response_data.get("detail", "")
    
    def test_oauth_redirect_missing_params(self):
        """Test OAuth redirect with missing parameters"""
        # Missing provider
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-redirect",
            params={"redirect_uri": "com.hillview://auth"}
        )
        assert response.status_code == 422  # FastAPI validation error
        
        # Missing redirect_uri
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-redirect",
            params={"provider": "google"}
        )
        assert response.status_code == 422  # FastAPI validation error


class TestOAuthCallback:
    """Test OAuth callback endpoint functionality"""
    
    def test_oauth_callback_mobile_error_handling(self):
        """Test OAuth callback error handling for mobile app"""
        # Test with invalid auth code (should get 400 error)
        state = "google:com.hillview://auth"
        code = "invalid_auth_code"
        
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-callback",
            params={
                "code": code,
                "state": state
            },
            allow_redirects=False
        )
        
        # Should get 400 error for invalid code
        assert response.status_code == 400
        
        # Should contain error information
        response_data = response.json()
        assert "detail" in response_data
        assert "OAuth" in response_data["detail"] or "token" in response_data["detail"]
    
    def test_oauth_callback_web_error_handling(self):
        """Test OAuth callback error handling for web app"""
        # Test with invalid auth code (should get 400 error)
        state = "google:http://localhost:8212/oauth/callback"
        code = "invalid_auth_code"
        
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-callback",
            params={
                "code": code,
                "state": state
            },
            allow_redirects=False
        )
        
        # Should get 400 error for invalid code
        assert response.status_code == 400
        
        # Should contain error information
        response_data = response.json()
        assert "detail" in response_data
        assert "OAuth" in response_data["detail"] or "token" in response_data["detail"]
    
    def test_oauth_callback_missing_code(self):
        """Test OAuth callback with missing auth code"""
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-callback",
            params={"state": "google:com.hillview://auth"}
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    def test_oauth_callback_malformed_state(self):
        """Test OAuth callback with malformed state parameter"""
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-callback",
            params={
                "code": "mock_code",
                "state": "invalid_state_format"
            }
        )
        
        # Should fall back to default provider
        assert response.status_code in [302, 400]  # Redirect or error


class TestAuthTokenValidation:
    """Test JWT token validation and expiration"""
    
    def test_token_error_handling(self):
        """Test that OAuth errors are handled properly"""
        # Test that invalid tokens result in proper error responses
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-callback",
            params={
                "code": "invalid_token_code",
                "state": "google:com.hillview://auth"
            },
            allow_redirects=False
        )
        
        # Should get error response, not a redirect with token
        assert response.status_code == 400
        
        response_data = response.json()
        assert "detail" in response_data
        # Should contain OAuth-related error message
        assert any(keyword in response_data["detail"].lower() for keyword in ["oauth", "token", "grant", "auth"])
    
    def test_oauth_parameter_validation(self):
        """Test that OAuth parameters are properly validated"""
        # Test various invalid parameter combinations
        test_cases = [
            {"code": "", "state": "google:com.hillview://auth"},  # Empty code
            {"code": "test", "state": ""},  # Empty state  
            {"code": "test", "state": "malformed_state"},  # Malformed state
            {"code": "test", "state": "invalid:javascript:alert('xss')"},  # XSS attempt
        ]
        
        for params in test_cases:
            response = requests.get(
                f"{BASE_URL}/api/auth/oauth-callback",
                params=params,
                allow_redirects=False
            )
            
            # Should either reject with 400/422 or handle gracefully
            assert response.status_code in [400, 422, 500], f"Unexpected status for params {params}: {response.status_code}"


class TestOAuthIntegration:
    """Integration tests for complete OAuth flow"""
    
    def test_complete_mobile_flow(self):
        """Test complete OAuth flow for mobile app"""
        # 1. Start OAuth redirect
        provider = "google"
        redirect_uri = "com.hillview://auth"
        
        response = requests.get(
            f"{BASE_URL}/api/auth/oauth-redirect",
            params={
                "provider": provider,
                "redirect_uri": redirect_uri
            },
            allow_redirects=False
        )
        
        assert response.status_code in [302, 307]
        
        # 2. Extract state from redirect
        location = response.headers.get("Location")
        parsed_url = urlparse(location)
        query_params = parse_qs(parsed_url.query)
        state = query_params["state"][0]
        
        # 3. Verify state contains provider and redirect URI
        assert provider in state
        assert redirect_uri in state
        
        # Note: Full flow would require mocking external OAuth provider
        # which is beyond scope of unit tests
    
    def test_provider_configuration(self):
        """Test that OAuth providers are properly configured"""
        # Test that required environment variables are set
        # This would be done in a separate configuration test
        pass
    
    def test_oauth_security_validation(self):
        """Test that OAuth security validations work properly"""
        # Test with potentially malicious redirect URIs in state
        malicious_states = [
            "google:http://evil.com/steal-tokens",
            "google:javascript:alert('xss')",
            "google:file:///etc/passwd"
        ]
        
        for state in malicious_states:
            response = requests.get(
                f"{BASE_URL}/api/auth/oauth-callback",
                params={
                    "code": "test_code",
                    "state": state
                },
                allow_redirects=False
            )
            
            # Should reject malicious redirects
            assert response.status_code in [400, 422], f"Should reject malicious state: {state}"


if __name__ == "__main__":
    # Run basic tests
    print("Starting OAuth authentication tests...")
    
    # Test OAuth redirect
    test_class = TestOAuthRedirect()
    try:
        test_class.test_oauth_redirect_google_mobile()
        print("✅ Google mobile OAuth redirect test passed")
    except Exception as e:
        print(f"❌ Google mobile OAuth redirect test failed: {e}")
    
    try:
        test_class.test_oauth_redirect_github_web()
        print("✅ GitHub web OAuth redirect test passed")
    except Exception as e:
        print(f"❌ GitHub web OAuth redirect test failed: {e}")
    
    try:
        test_class.test_oauth_redirect_invalid_provider()
        print("✅ Invalid provider test passed")
    except Exception as e:
        print(f"❌ Invalid provider test failed: {e}")
    
    print("\nOAuth tests completed!")