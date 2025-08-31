#!/usr/bin/env python3
"""Unit tests for security features using FastAPI TestClient."""

import warnings
# Suppress specific deprecation warnings that we cannot fix at our level
warnings.filterwarnings("ignore", message="'crypt' is deprecated", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="Support for class-based `config` is deprecated", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="The 'app' shortcut is now deprecated", category=DeprecationWarning)

import pytest
import os
import sys

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Enable user accounts for authentication testing
os.environ["USER_ACCOUNTS"] = "true"

from fastapi.testclient import TestClient
from api.app.api import app

# Create TestClient for unit testing
client = TestClient(app)


class TestSecurityHeaders:
    """Test security headers using FastAPI TestClient"""
    
    def test_security_headers_on_debug_endpoint(self):
        """Test that security headers are present on debug endpoint"""
        response = client.get("/api/debug")
        
        # Check for security headers
        headers = response.headers
        
        # These headers should be present
        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options", 
            "X-XSS-Protection"
        ]
        
        for header in expected_headers:
            assert header in headers, f"Missing security header: {header}"
    
    def test_security_headers_on_api_endpoints(self):
        """Test that security headers are present on API endpoints"""
        response = client.get("/api/mapillary")
        
        headers = response.headers
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers


class TestInputValidation:
    """Test input validation using FastAPI TestClient"""
    
    def test_invalid_registration_data(self):
        """Test that invalid registration data is rejected"""
        invalid_users = [
            {"username": "a", "email": "test@test.com", "password": "Test1234!"},  # Too short
            {"username": "user@123", "email": "test@test.com", "password": "Test1234!"},  # Invalid chars
            {"username": "a" * 50, "email": "test@test.com", "password": "Test1234!"},  # Too long
        ]
        
        for user in invalid_users:
            response = client.post("/api/auth/register", json=user)
            # Should be rejected with 400 or 422
            assert response.status_code in [400, 422], f"Should reject invalid user: {user['username']}"
    
    def test_invalid_email_formats(self):
        """Test that invalid email formats are rejected"""
        invalid_emails = [
            "notanemail",
            "@nodomain.com",
            "no@.com",
            "spaces @domain.com"
        ]
        
        for email in invalid_emails:
            user_data = {
                "username": "validuser",
                "email": email,
                "password": "ValidPass123!"
            }
            response = client.post("/api/auth/register", json=user_data)
            assert response.status_code in [400, 422], f"Should reject invalid email: {email}"
    


class TestPathTraversal:
    """Test path traversal protection using FastAPI TestClient"""
    
    def test_path_traversal_attempts(self):
        """Test that path traversal attempts are blocked"""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "....//....//....//etc//passwd"
        ]
        
        for path in malicious_paths:
            # Try different endpoints that might accept file paths
            response = client.get(f"/api/photos/{path}")
            # Should not return sensitive files (404 or 400 is fine)
            assert response.status_code != 200 or "root:" not in response.text, f"Path traversal vulnerability with: {path}"