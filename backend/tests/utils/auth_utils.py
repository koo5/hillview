#!/usr/bin/env python3
"""
Shared authentication utilities for tests.
Consolidates common authentication patterns to reduce duplication.
"""
import os
import requests
from typing import Dict, Optional, Tuple
from .test_utils import recreate_test_users, API_URL

# Standard test credentials
TEST_CREDENTIALS = {
    "test": "StrongTestPassword123!",
    "admin": "StrongAdminPassword123!"
}

class AuthTestHelper:
    """Helper class for authentication operations in tests."""
    
    def __init__(self, api_url: str = None):
        self.api_url = api_url or API_URL
        self._tokens_cache = {}
    
    def get_auth_headers(self, token: str) -> Dict[str, str]:
        """Get authorization headers with Bearer token."""
        return {"Authorization": f"Bearer {token}"}
    
    def get_test_user_token(self, username: str = "test") -> str:
        """Get a valid token for test user."""
        if username in self._tokens_cache:
            return self._tokens_cache[username]
            
        if username not in TEST_CREDENTIALS:
            raise ValueError(f"Unknown test user: {username}")
        
        login_data = {
            "username": username,
            "password": TEST_CREDENTIALS[username]
        }
        
        response = requests.post(
            f"{self.api_url}/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get token for {username}: {response.status_code} - {response.text}")
        
        token = response.json()["access_token"]
        self._tokens_cache[username] = token
        return token
    
    def get_admin_token(self) -> str:
        """Get a valid token for admin user."""
        return self.get_test_user_token("admin")
    
    def get_tokens_for_different_users(self) -> Tuple[str, str]:
        """Get tokens for test and admin users, ensuring users exist."""
        # Ensure test users exist
        recreate_test_users()
        
        test_token = self.get_test_user_token("test")
        admin_token = self.get_test_user_token("admin")
        
        return test_token, admin_token
    
    def clear_token_cache(self):
        """Clear cached tokens (useful between tests)."""
        self._tokens_cache.clear()
    
    def test_token_validity(self, token: str) -> bool:
        """Test if a token is valid by making a protected API call."""
        try:
            response = requests.get(
                f"{self.api_url}/user/profile",
                headers=self.get_auth_headers(token)
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def login_user(self, username: str, password: str) -> Dict:
        """Login with username/password and return full response."""
        login_data = {
            "username": username,
            "password": password
        }
        
        response = requests.post(
            f"{self.api_url}/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        return {
            "status_code": response.status_code,
            "response": response,
            "token": response.json().get("access_token") if response.status_code == 200 else None
        }

# Global instance for convenience
auth_helper = AuthTestHelper()

# Convenience functions for backward compatibility
def get_auth_headers(token: str) -> Dict[str, str]:
    """Get authorization headers with Bearer token."""
    return auth_helper.get_auth_headers(token)

def get_test_user_token() -> str:
    """Get a valid token for test user."""
    return auth_helper.get_test_user_token()

def get_admin_token() -> str:
    """Get a valid token for admin user."""
    return auth_helper.get_admin_token()

def get_tokens_for_different_users() -> Tuple[str, str]:
    """Get tokens for test and admin users."""
    return auth_helper.get_tokens_for_different_users()