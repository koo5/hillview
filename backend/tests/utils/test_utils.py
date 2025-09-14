#!/usr/bin/env python3
"""
Shared utilities for hidden content tests.
"""

import os
import requests
import json
from PIL import Image
import piexif
import io
import pytest

# Test configuration
API_URL = os.getenv("API_URL", "http://localhost:8055/api")

def clear_test_database():
	"""Clear the database before running tests. Fails test on error."""
	print("Clearing database...")
	try:
		response = requests.post(f"{API_URL}/debug/clear-database")
		if response.status_code == 200:
			details = response.json().get("details", {})
			print(f"✓ Database cleared: {details}")
			return response.json()
		else:
			print(f"⚠️  Database clear failed: {response.status_code} - {response.text}")
			pytest.fail(f"clear-database failed: {response.status_code} - {response.text}")
	except Exception as e:
		print(f"❌ Failed to clear database: {e}")
		pytest.fail(f"clear-database failed with exception: {e}")

def recreate_test_users():
	"""Recreate test users using the debug endpoint. Fails test on error."""
	print("Recreating test users using debug endpoint...")
	try:
		response = requests.post(f"{API_URL}/debug/recreate-test-users")
		if response.status_code == 200:
			result = response.json()
			print(f"✅ Test users reset successfully: {result}")
			details = result.get("details", {}) or {}
			photos_deleted = details.get("photos_deleted", 0)
			users_deleted = details.get("users_deleted", 0)
			users_created = details.get("users_created", 0)
			print(f"   - {photos_deleted} photos deleted")
			print(f"   - {users_deleted} old users deleted")
			print(f"   - {users_created} new users created")
			print("Test user reset complete")
			return result
		else:
			print(f"⚠️  Test user reset failed: {response.status_code} - {response.text}")
			print("Make sure DEBUG_ENDPOINTS=true and TEST_USERS=true")
			pytest.fail(f"recreate-test-users failed: {response.status_code} - {response.text}")
	except Exception as e:
		print(f"❌ Failed to setup test users: {e}")
		pytest.fail(f"recreate-test-users failed with exception: {e}")

def create_test_image(width: int = 100, height: int = 100, color: tuple = (255, 0, 0),
					  lat: float = 50.0755, lon: float = 14.4378) -> bytes:
	"""Create a real JPEG image with GPS coordinates for testing."""
	# Create a simple colored image
	img = Image.new('RGB', (width, height), color)

	# Convert coordinates to GPS EXIF format
	def decimal_to_dms(decimal_deg):
		"""Convert decimal degrees to degrees, minutes, seconds."""
		deg = int(decimal_deg)
		minutes = abs((decimal_deg - deg) * 60)
		min_int = int(minutes)
		sec = (minutes - min_int) * 60
		return [(deg, 1), (min_int, 1), (int(sec * 100), 100)]

	# Create GPS EXIF data (Prague coordinates by default)
	gps_dict = {
		piexif.GPSIFD.GPSLatitude: decimal_to_dms(abs(lat)),
		piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
		piexif.GPSIFD.GPSLongitude: decimal_to_dms(abs(lon)),
		piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
	}

	exif_dict = {"GPS": gps_dict}
	exif_bytes = piexif.dump(exif_dict)

	# Save to bytes buffer with GPS EXIF
	img_buffer = io.BytesIO()
	img.save(img_buffer, format='JPEG', quality=85, exif=exif_bytes)
	img_buffer.seek(0)

	return img_buffer.getvalue()

async def create_test_photos(test_users: list, auth_tokens: dict):
	"""Create test photos by uploading real images using the secure upload workflow."""
	from .secure_upload_utils import SecureUploadClient

	print("Creating test photos for filtering tests using secure upload workflow...")

	# Create test photos for different users with different colors and GPS coordinates in Prague area
	test_photos_data = [
		("test_photo_1.jpg", "Test photo 1 for filtering", True, (255, 0, 0), 50.0755, 14.4378),   # Red - Prague Castle
		("test_photo_2.jpg", "Test photo 2 for filtering", True, (0, 255, 0), 50.0865, 14.4175),   # Green - Old Town Square
		("test_photo_3.jpg", "Test photo 3 for filtering", False, (0, 0, 255), 50.0819, 14.4362),  # Blue (private) - Wenceslas Square
		("test_photo_4.jpg", "Test photo 4 for filtering", True, (255, 255, 0), 50.0870, 14.4208), # Yellow - Charles Bridge
	]

	# Create SecureUploadClient instance
	upload_client = SecureUploadClient(api_url=API_URL)

	created_photos = 0
	for i, (filename, description, is_public, color, lat, lon) in enumerate(test_photos_data):
		# Assign photos to different users for variety
		user_index = i % len(test_users)
		username = test_users[user_index]["username"]

		# Get auth token
		token = auth_tokens.get(username)
		if not token:
			raise Exception(f"No token found for user {username}")

		# Create a real JPEG image with GPS coordinates AND bearing (for successful processing)
		from .image_utils import create_test_image_full_gps
		bearing = 45.0 + (i * 30)  # Different bearings: 45°, 75°, 105°, 135°
		image_data = create_test_image_full_gps(200, 150, color, lat, lon, bearing)

		# Use secure upload workflow
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(token, client_keys)

		auth_data = await upload_client.authorize_upload_with_params(
			token, filename, len(image_data), lat, lon, description, is_public, file_data=image_data
		)

		result = await upload_client.upload_to_worker(image_data, auth_data, client_keys, filename)
		photo_id = result.get('photo_id', auth_data.get('photo_id', 'unknown'))
		print(f"✓ Uploaded photo: {filename} by {username} (ID: {photo_id})")

		# Wait for processing to complete
		photo_data = wait_for_photo_processing(photo_id, token, timeout=30)
		if photo_data['processing_status'] == 'completed':
			created_photos += 1
			print(f"  ✓ Processed: lat={photo_data.get('latitude')}, lon={photo_data.get('longitude')}, bearing={photo_data.get('compass_angle')}")
		else:
			error_msg = photo_data.get('error', 'Unknown error')
			raise Exception(f"Photo processing failed: {error_msg}")

	print(f"✓ Created {created_photos} test photos using secure upload workflow")
	return created_photos


def wait_for_photo_processing(photo_id: str, token: str, timeout: int = 30) -> dict:
	"""Poll the photo endpoint until processing is complete or timeout."""
	import time

	headers = {"Authorization": f"Bearer {token}"}
	start_time = time.time()

	while time.time() - start_time < timeout:
		try:
			response = requests.get(f"{API_URL}/photos/{photo_id}", headers=headers)
			if response.status_code == 200:
				photo_data = response.json()
				status = photo_data.get('processing_status', 'unknown')

				if status in ['completed', 'error']:
					return photo_data

				print(f"Photo {photo_id} still processing (status: {status}), waiting...")
				time.sleep(2)
			else:
				print(f"Failed to fetch photo {photo_id}: {response.status_code}")
				time.sleep(2)

		except Exception as e:
			print(f"Error polling photo {photo_id}: {e}")
			time.sleep(2)

	raise Exception(f"Timeout waiting for photo {photo_id} processing after {timeout}s")


async def upload_test_image(filename: str, image_data: bytes, description: str, token: str, is_public: bool = True, timeout: float = 60.0) -> str:
	"""Upload a test image using secure upload workflow and return the photo ID."""
	from .secure_upload_utils import SecureUploadClient

	upload_client = SecureUploadClient(api_url=API_URL)

	try:
		# Generate client keys
		client_keys = upload_client.generate_client_keys()

		# Register client key
		await upload_client.register_client_key(token, client_keys)

		# Authorize upload with default coordinates
		auth_data = await upload_client.authorize_upload_with_params(
			token,
			filename,
			len(image_data),
			50.0755,  # Default Prague latitude
			14.4378,  # Default Prague longitude
			description,
			is_public,
			file_data=image_data  # Pass the actual file data for MD5 calculation
		)

		# Upload to worker
		result = await upload_client.upload_to_worker(
			image_data, auth_data, client_keys, filename, timeout=timeout
		)

		photo_id = result.get('photo_id')
		if not photo_id:
			raise Exception(f"No photo ID returned from secure upload: {result}")

		return photo_id

	except Exception as e:
		# Get more detailed error information
		error_type = type(e).__name__
		error_msg = str(e) if str(e) else "No error message"

		# Handle specific httpx exceptions with better messages
		import httpx
		if isinstance(e, httpx.ReadTimeout):
			error_msg = "HTTP read timeout - worker took too long to respond"
		elif isinstance(e, httpx.ConnectTimeout):
			error_msg = "HTTP connect timeout - could not connect to worker"
		elif isinstance(e, httpx.ConnectError):
			error_msg = "HTTP connection error - worker not reachable"
		elif isinstance(e, httpx.HTTPError) and not error_msg:
			error_msg = f"HTTP client error"

		raise Exception(f"[test_utils] Upload failed: {error_type}: {error_msg}")


def query_hillview_endpoint(token: str = None, params: dict = None) -> dict:
	"""
	Query the hillview endpoint and parse SSE response format.

	Args:
		token: Authentication token (optional)
		params: Query parameters for the hillview endpoint

	Returns:
		dict: Parsed response with 'photos' list and metadata
	"""
	headers = {
		"Accept": "text/event-stream",
		"Cache-Control": "no-cache"
	}

	if token:
		headers["Authorization"] = f"Bearer {token}"

	response = requests.get(
		f"{API_URL}/hillview",
		params=params,
		headers=headers,
		stream=True
	)

	if response.status_code != 200:
		raise Exception(f"Hillview endpoint failed: {response.status_code} - {response.text}")

	# Parse SSE stream format
	photos_data = None
	total_count = 0

	for line in response.iter_lines(decode_unicode=True):
		if line and line.startswith('data: '):
			try:
				line_data = json.loads(line[6:])  # Remove 'data: ' prefix
				if line_data.get('type') == 'photos':
					photos_data = line_data
					total_count = len(line_data.get('photos', []))
				elif line_data.get('type') == 'stream_complete':
					break
			except json.JSONDecodeError:
				continue

	if not photos_data:
		return {'photos': [], 'total_count': 0}

	return {
		'photos': photos_data.get('photos', []),
		'total_count': total_count,
		'data': photos_data.get('photos', [])  # For backward compatibility
	}
