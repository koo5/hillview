#!/usr/bin/env python3
"""
Test photo processing error cases with polling mechanism.
"""

import pytest
import requests
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.test_utils import clear_test_database, API_URL, upload_test_image, wait_for_photo_processing, recreate_test_users
from utils.image_utils import (
	create_test_image_no_exif,
	create_test_image_coords_only,
	create_test_image_bearing_only,
	create_test_image_full_gps,
	create_test_image_corrupted_exif
)


def setup_test_user():
	"""Create test users and return auth token."""
	recreate_test_users()
	
	# Login as standard test user
	login_data = {"username": "test", "password": "StrongTestPassword123!"}
	response = requests.post(f"{API_URL}/auth/token", data=login_data)
	if response.status_code != 200:
		raise Exception(f"Failed to login test user: {response.status_code} - {response.text}")

	token_data = response.json()
	return token_data["access_token"]


@pytest.mark.asyncio
async def test_no_exif_data():
	"""Test error message for images with no EXIF data."""
	print("Testing: No EXIF data error case")

	token = setup_test_user()

	# Create image with no EXIF data
	image_data = create_test_image_no_exif(color=(255, 0, 0))

	# Upload image
	photo_id = await upload_test_image("no_exif_test.jpg", image_data, "Test image without EXIF", token)
	print(f"✓ Uploaded photo {photo_id}")

	# Wait for processing
	photo_data = wait_for_photo_processing(photo_id, token, timeout=30)

	# Verify error message
	assert photo_data['processing_status'] == 'error', f"Expected error status, got {photo_data['processing_status']}"
	error_msg = photo_data.get('error', '')
	expected_msg = "No EXIF data found in image file"
	assert expected_msg in error_msg, f"Expected '{expected_msg}' in error message, got: {error_msg}"

	print(f"✓ Correct error message: {error_msg}")
	print("✓ No EXIF data test passed\n")


@pytest.mark.asyncio
async def test_missing_gps_coordinates():
	"""Test error message for images with bearing but no GPS coordinates."""
	print("Testing: Missing GPS coordinates error case")

	token = setup_test_user()

	# Create image with bearing but no coordinates
	image_data = create_test_image_bearing_only(color=(0, 0, 255))

	# Upload image
	photo_id = await upload_test_image("bearing_only_test.jpg", image_data, "Test image with bearing only", token)
	print(f"✓ Uploaded photo {photo_id}")

	# Wait for processing
	photo_data = wait_for_photo_processing(photo_id, token, timeout=30)

	# Verify error message shows found bearing tags and missing coordinates
	assert photo_data['processing_status'] == 'error', f"Expected error status, got {photo_data['processing_status']}"
	error_msg = photo_data.get('error', '')
	expected_msg = "GPS coordinates missing"
	assert expected_msg in error_msg, f"Expected '{expected_msg}' in error message, got: {error_msg}"
	assert "GPS GPSImgDirection" in error_msg, f"Expected found bearing tag in error message, got: {error_msg}"
	assert "GPSLatitude, GPSLongitude" in error_msg, f"Expected coordinate requirements in error message, got: {error_msg}"

	print(f"✓ Correct error message: {error_msg}")
	print("✓ Missing GPS coordinates test passed\n")


@pytest.mark.asyncio
async def test_missing_bearing_data():
	"""Test error message for images with GPS coordinates but no bearing."""
	print("Testing: Missing bearing data error case")

	token = setup_test_user()

	# Create image with coordinates but no bearing
	image_data = create_test_image_coords_only(color=(0, 255, 0))

	# Upload image
	photo_id = await upload_test_image("coords_only_test.jpg", image_data, "Test image with coordinates only", token)
	print(f"✓ Uploaded photo {photo_id}")

	# Wait for processing
	photo_data = wait_for_photo_processing(photo_id, token, timeout=30)

	# Verify error message
	assert photo_data['processing_status'] == 'error', f"Expected error status, got {photo_data['processing_status']}"
	error_msg = photo_data.get('error', '')
	expected_msg = "Compass direction missing"
	assert expected_msg in error_msg, f"Expected '{expected_msg}' in error message, got: {error_msg}"
	assert "GPSImgDirection, GPSTrack, or GPSDestBearing" in error_msg, f"Expected bearing requirements in error message, got: {error_msg}"

	print(f"✓ Correct error message: {error_msg}")
	print("✓ Missing bearing data test passed\n")


@pytest.mark.asyncio
async def test_successful_processing():
	"""Test successful processing with full GPS data."""
	print("Testing: Successful processing with full GPS data")

	token = setup_test_user()

	# Create image with full GPS data
	image_data = create_test_image_full_gps(color=(255, 255, 0), lat=50.0755, lon=14.4378, bearing=90.0)

	# Upload image
	photo_id = await upload_test_image("full_gps_test.jpg", image_data, "Test image with full GPS data", token)
	print(f"✓ Uploaded photo {photo_id}")

	# Wait for processing
	photo_data = wait_for_photo_processing(photo_id, token, timeout=30)

	# Verify successful processing
	assert photo_data['processing_status'] == 'completed', f"Expected completed status, got {photo_data['processing_status']}"
	assert photo_data.get('error') is None, f"Expected no error, got: {photo_data.get('error')}"
	assert photo_data.get('latitude') is not None, "Expected latitude to be set"
	assert photo_data.get('longitude') is not None, "Expected longitude to be set"
	assert photo_data.get('compass_angle') is not None, "Expected compass_angle to be set"

	print(f"✓ Successfully processed: lat={photo_data['latitude']}, lon={photo_data['longitude']}, bearing={photo_data['compass_angle']}")
	print("✓ Successful processing test passed\n")


@pytest.mark.asyncio
async def test_corrupted_exif_handling():
	"""Test handling of corrupted EXIF data."""
	print("Testing: Corrupted EXIF data handling")

	token = setup_test_user()

	# Create image with potentially corrupted EXIF
	image_data = create_test_image_corrupted_exif(color=(255, 0, 255))

	# Upload image
	photo_id = await upload_test_image("corrupted_exif_test.jpg", image_data, "Test image with corrupted EXIF", token)
	print(f"✓ Uploaded photo {photo_id}")

	# Wait for processing
	photo_data = wait_for_photo_processing(photo_id, token, timeout=30)

	# Should either process successfully or fail gracefully with descriptive error
	status = photo_data['processing_status']
	if status == 'error':
		error_msg = photo_data.get('error', '')
		# Should have a meaningful error message, not a raw exception
		assert len(error_msg) > 0, "Expected non-empty error message"
		assert "Traceback" not in error_msg, f"Error message should not contain raw traceback: {error_msg}"
		print(f"✓ Graceful error handling: {error_msg}")
	else:
		print(f"✓ Successfully processed despite potential corruption")

	print("✓ Corrupted EXIF handling test passed\n")


def run_all_tests():
	"""Run all photo processing error tests."""
	print("Running photo processing error tests...\n")

	try:
		test_no_exif_data()
		test_missing_gps_coordinates()
		test_missing_bearing_data()
		test_successful_processing()
		test_corrupted_exif_handling()

		print("🎉 All photo processing error tests passed!")

	except Exception as e:
		print(f"❌ Test failed: {e}")
		raise


if __name__ == "__main__":
	run_all_tests()
