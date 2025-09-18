"""
Consolidated API client for tests and debugging.
Eliminates duplication of API calls across test utilities.
"""

import requests
import logging
from typing import Optional, Dict, Any, List
from .auth_utils import auth_helper
from .test_utils import API_URL

logger = logging.getLogger(__name__)


class APIClient:
	"""Centralized API client for all test operations."""

	def __init__(self, api_url: str = API_URL):
		self.api_url = api_url
		self.auth = auth_helper

	def get_headers(self, token: str) -> Dict[str, str]:
		"""Get headers with authentication token."""
		return {"Authorization": f"Bearer {token}"}

	# Photo Operations
	def get_photos(self, token: str, limit: int = 20, cursor: Optional[str] = None, timeout: float = 5.0) -> Dict[str, Any]:
		"""Get user's photos with pagination."""
		params = {"limit": limit}
		if cursor:
			params["cursor"] = cursor

		url = f"{self.api_url}/photos"
		logger.debug(f"GET {url} (timeout={timeout}s)")
		response = requests.get(
			url,
			headers=self.get_headers(token),
			params=params,
			timeout=timeout
		)
		response.raise_for_status()
		return response.json()

	def get_photo_details(self, photo_id: str, token: str, timeout: float = 5.0) -> Dict[str, Any]:
		"""Get detailed info about a specific photo."""
		url = f"{self.api_url}/photos/{photo_id}"
		logger.debug(f"GET {url} (timeout={timeout}s)")
		response = requests.get(
			url,
			headers=self.get_headers(token),
			timeout=timeout
		)
		response.raise_for_status()
		return response.json()

	def delete_photo(self, photo_id: str, token: str, timeout: float = 5.0) -> Dict[str, Any]:
		"""Delete a photo."""
		url = f"{self.api_url}/photos/{photo_id}"
		logger.debug(f"DELETE {url} (timeout={timeout}s)")
		response = requests.delete(
			url,
			headers=self.get_headers(token),
			timeout=timeout
		)
		response.raise_for_status()
		return response.json()

	# User Operations
	def get_user_profile(self, token: str, timeout: float = 5.0) -> Dict[str, Any]:
		"""Get user profile."""
		url = f"{self.api_url}/user/profile"
		logger.debug(f"GET {url} (timeout={timeout}s)")
		response = requests.get(
			url,
			headers=self.get_headers(token),
			timeout=timeout
		)
		response.raise_for_status()
		return response.json()

	def delete_user(self, token: str, timeout: float = 5.0) -> Dict[str, Any]:
		"""Delete user account."""
		url = f"{self.api_url}/user/delete"
		logger.debug(f"DELETE {url} (timeout={timeout}s)")
		response = requests.delete(
			url,
			headers=self.get_headers(token),
			timeout=timeout
		)
		response.raise_for_status()
		return response.json()

	# Debug Operations
	def recreate_test_users(self, timeout: float = 5.0) -> Dict[str, Any]:
		"""Recreate test users."""
		url = f"{self.api_url}/debug/recreate-test-users"
		logger.debug(f"POST {url} (timeout={timeout}s)")
		response = requests.post(url, timeout=timeout)
		response.raise_for_status()
		return response.json()

	def clear_database(self, timeout: float = 5.0) -> Dict[str, Any]:
		"""Clear database."""
		url = f"{self.api_url}/debug/clear-database"
		logger.debug(f"POST {url} (timeout={timeout}s)")
		response = requests.post(url, timeout=timeout)
		response.raise_for_status()
		return response.json()

	# Convenience Methods
	def get_error_photos(self, token: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
		"""Get all photos with processing errors."""
		photos_data = self.get_photos(token, limit=100, timeout=timeout)
		return [p for p in photos_data.get('photos', [])
				if p.get('processing_status') == 'error']

	def cleanup_user_photos(self, token: str, timeout: float = 5.0) -> int:
		"""Delete all user's photos. Returns count of deleted photos."""
		photos_data = self.get_photos(token, limit=100, timeout=timeout)
		photos = photos_data.get('photos', [])

		deleted_count = 0
		for photo in photos:
			try:
				self.delete_photo(photo['id'], token, timeout=timeout)
				deleted_count += 1
			except requests.RequestException:
				pass  # Continue with other photos

		return deleted_count

	def wait_for_photo_processing(self, photo_id: str, token: str, timeout: int = 30, request_timeout: float = 5.0) -> Dict[str, Any]:
		"""Wait for photo processing to complete. Returns final photo data."""
		import time

		start_time = time.time()
		while time.time() - start_time < timeout:
			try:
				photo = self.get_photo_details(photo_id, token, timeout=request_timeout)
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
def get_photos_with_client(token: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
	"""Get photos using the centralized client."""
	return api_client.get_photos(token, timeout=timeout).get('photos', [])

def get_photo_details_with_client(photo_id: str, token: str, timeout: float = 5.0) -> Dict[str, Any]:
	"""Get photo details using the centralized client."""
	return api_client.get_photo_details(photo_id, token, timeout=timeout)

def cleanup_all_photos(token: str, timeout: float = 5.0) -> int:
	"""Clean up all photos for a user."""
	return api_client.cleanup_user_photos(token, timeout=timeout)
