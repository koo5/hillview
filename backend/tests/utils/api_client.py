"""
Consolidated API client for tests and debugging.
Eliminates duplication of API calls across test utilities.
"""

import requests
from typing import Optional, Dict, Any, List
from .auth_utils import auth_helper
from .test_utils import API_URL


class APIClient:
    """Centralized API client for all test operations."""

    def __init__(self, api_url: str = API_URL):
        self.api_url = api_url
        self.auth = auth_helper

    def get_headers(self, token: str) -> Dict[str, str]:
        """Get headers with authentication token."""
        return {"Authorization": f"Bearer {token}"}

    # Photo Operations
    def get_photos(self, token: str, limit: int = 20, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Get user's photos with pagination."""
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            f"{self.api_url}/photos",
            headers=self.get_headers(token),
            params=params
        )
        response.raise_for_status()
        return response.json()

    def get_photo_details(self, photo_id: str, token: str) -> Dict[str, Any]:
        """Get detailed info about a specific photo."""
        response = requests.get(
            f"{self.api_url}/photos/{photo_id}",
            headers=self.get_headers(token)
        )
        response.raise_for_status()
        return response.json()

    def delete_photo(self, photo_id: str, token: str) -> Dict[str, Any]:
        """Delete a photo."""
        response = requests.delete(
            f"{self.api_url}/photos/{photo_id}",
            headers=self.get_headers(token)
        )
        response.raise_for_status()
        return response.json()

    # User Operations
    def get_user_profile(self, token: str) -> Dict[str, Any]:
        """Get user profile."""
        response = requests.get(
            f"{self.api_url}/user/profile",
            headers=self.get_headers(token)
        )
        response.raise_for_status()
        return response.json()

    def delete_user(self, token: str) -> Dict[str, Any]:
        """Delete user account."""
        response = requests.delete(
            f"{self.api_url}/user/delete",
            headers=self.get_headers(token)
        )
        response.raise_for_status()
        return response.json()

    # Debug Operations
    def recreate_test_users(self) -> Dict[str, Any]:
        """Recreate test users."""
        response = requests.post(f"{self.api_url}/debug/recreate-test-users")
        response.raise_for_status()
        return response.json()

    def clear_database(self) -> Dict[str, Any]:
        """Clear database."""
        response = requests.post(f"{self.api_url}/debug/clear-database")
        response.raise_for_status()
        return response.json()

    # Convenience Methods
    def get_error_photos(self, token: str) -> List[Dict[str, Any]]:
        """Get all photos with processing errors."""
        photos_data = self.get_photos(token, limit=100)
        return [p for p in photos_data.get('photos', [])
                if p.get('processing_status') == 'error']

    def cleanup_user_photos(self, token: str) -> int:
        """Delete all user's photos. Returns count of deleted photos."""
        photos_data = self.get_photos(token, limit=100)
        photos = photos_data.get('photos', [])

        deleted_count = 0
        for photo in photos:
            try:
                self.delete_photo(photo['id'], token)
                deleted_count += 1
            except requests.RequestException:
                pass  # Continue with other photos

        return deleted_count

    def wait_for_photo_processing(self, photo_id: str, token: str, timeout: int = 30) -> Dict[str, Any]:
        """Wait for photo processing to complete. Returns final photo data."""
        import time

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                photo = self.get_photo_details(photo_id, token)
                status = photo.get('processing_status', 'unknown')

                if status in ['completed', 'error']:
                    return photo

                time.sleep(2)
            except requests.RequestException:
                time.sleep(2)

        raise TimeoutError(f"Photo {photo_id} processing timed out after {timeout}s")


# Global instance for convenience
api_client = APIClient()


# Convenience functions for backward compatibility
def get_photos_with_client(token: str) -> List[Dict[str, Any]]:
    """Get photos using the centralized client."""
    return api_client.get_photos(token).get('photos', [])

def get_photo_details_with_client(photo_id: str, token: str) -> Dict[str, Any]:
    """Get photo details using the centralized client."""
    return api_client.get_photo_details(photo_id, token)

def cleanup_all_photos(token: str) -> int:
    """Clean up all photos for a user."""
    return api_client.cleanup_user_photos(token)