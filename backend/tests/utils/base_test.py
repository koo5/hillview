#!/usr/bin/env python3
"""
Base test classes providing common functionality for integration tests.
Reduces duplication and provides consistent test setup/teardown.
"""
import unittest
import asyncio
from typing import Dict, List, Optional
from tests.utils.test_utils import recreate_test_users, API_URL
from tests.utils.auth_utils import AuthTestHelper, TEST_CREDENTIALS

class BaseIntegrationTest(unittest.TestCase):
    """Base class for integration tests with common setup and utilities."""
    
    @classmethod
    def setUpClass(cls):
        """Class-level setup run once before all tests in the class."""
        cls.api_url = API_URL
        cls.auth_helper = AuthTestHelper(cls.api_url)
        cls.test_credentials = TEST_CREDENTIALS.copy()
    
    def setUp(self):
        """Setup run before each test method."""
        # Clear token cache to ensure fresh tokens for each test
        self.auth_helper.clear_token_cache()
        # Ensure test users exist for each test
        recreate_test_users()
    
    def setup_method(self, method=None):
        """Pytest-compatible setup method."""
        self.setUp()
    
    def tearDown(self):
        """Cleanup run after each test method."""
        # Clear token cache
        self.auth_helper.clear_token_cache()
    
    def teardown_method(self, method=None):
        """Pytest-compatible teardown method."""
        self.tearDown()
    
    # Common utility methods
    def get_auth_headers(self, token: str) -> Dict[str, str]:
        """Get authorization headers with Bearer token."""
        return self.auth_helper.get_auth_headers(token)
    
    def get_test_token(self, username: str = "test") -> str:
        """Get a valid token for specified test user."""
        return self.auth_helper.get_test_user_token(username)
    
    def get_admin_token(self) -> str:
        """Get a valid token for admin user."""
        return self.auth_helper.get_admin_token()
    
    def get_different_user_tokens(self) -> tuple[str, str]:
        """Get tokens for test and admin users."""
        return self.auth_helper.get_tokens_for_different_users()
    
    def assert_unauthorized(self, response, message: str = "Should be unauthorized"):
        """Assert that response has 401 status code."""
        self.assertEqual(response.status_code, 401, message)
    
    def assert_success(self, response, message: str = "Should be successful"):
        """Assert that response has 200 status code."""
        self.assertEqual(response.status_code, 200, message)
    
    def assert_bad_request(self, response, message: str = "Should be bad request"):
        """Assert that response has 400 status code."""
        self.assertEqual(response.status_code, 400, message)
    
    def assert_forbidden(self, response, message: str = "Should be forbidden"):
        """Assert that response has 403 status code."""
        self.assertEqual(response.status_code, 403, message)

class BaseAuthTest(BaseIntegrationTest):
    """Base class specifically for authentication-related tests."""
    
    def setUp(self):
        """Setup for auth tests with additional auth-specific setup."""
        super().setUp()
        # Pre-populate common tokens for auth tests
        self.test_token = self.get_test_token()
        self.admin_token = self.get_admin_token()
        self.test_headers = self.get_auth_headers(self.test_token)
        self.admin_headers = self.get_auth_headers(self.admin_token)
    
    def setup_method(self, method=None):
        """Pytest-compatible setup method."""
        self.setUp()
    
    def teardown_method(self, method=None):
        """Pytest-compatible teardown method."""
        self.tearDown()

class BasePhotoTest(BaseIntegrationTest):
    """Base class for photo-related tests with photo utilities."""
    
    def setUp(self):
        """Setup for photo tests."""
        super().setUp()
        self.test_token = self.get_test_token()
        self.test_headers = self.get_auth_headers(self.test_token)
    
    def setup_method(self, method=None):
        """Pytest-compatible setup method."""
        self.setUp()
    
    def teardown_method(self, method=None):
        """Pytest-compatible teardown method."""
        self.tearDown()
    
    async def create_test_photos_async(self, users: List[dict], tokens: Dict[str, str]) -> int:
        """Create test photos for filtering tests."""
        from .test_utils import create_test_photos
        return await create_test_photos(users, tokens)
    
    def create_test_photos(self, users: List[dict], tokens: Dict[str, str]) -> int:
        """Synchronous wrapper for creating test photos."""
        return asyncio.run(self.create_test_photos_async(users, tokens))

class BaseUserManagementTest(BaseIntegrationTest):
    """Base class for user management tests."""
    
    def setUp(self):
        """Setup for user management tests."""
        super().setUp()
        # Create both test users for user isolation tests
        self.test_token, self.admin_token = self.get_different_user_tokens()
        self.test_headers = self.get_auth_headers(self.test_token)
        self.admin_headers = self.get_auth_headers(self.admin_token)
        
        # Store test user info for reference
        self.test_users = [
            {"username": "test", "password": "StrongTestPassword123!"},
            {"username": "admin", "password": "StrongAdminPassword123!"}
        ]
        
        self.auth_tokens = {
            "test": self.test_token,
            "admin": self.admin_token
        }
    
    def setup_method(self, method=None):
        """Pytest-compatible setup method."""
        self.setUp()
    
    def teardown_method(self, method=None):
        """Pytest-compatible teardown method."""
        self.tearDown()
    
    async def create_test_photos_async(self, users: List[dict], tokens: Dict[str, str]) -> int:
        """Create test photos for filtering tests."""
        from .test_utils import create_test_photos
        return await create_test_photos(users, tokens)
    
    def create_test_photos(self, users: List[dict], tokens: Dict[str, str]) -> int:
        """Synchronous wrapper for creating test photos."""
        import asyncio
        return asyncio.run(self.create_test_photos_async(users, tokens))