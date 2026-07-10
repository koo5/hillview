#!/usr/bin/env python3
"""
Integration tests for the worker's async upload endpoint (POST /upload_async).

Unlike /upload (sync), /upload_async accepts the multipart body, returns
{'success': True} immediately, and processes the photo in a background task
that reports the result to the API server's /photos/processed. Clients (the
JS/Kotlin apps) then poll the API photo status endpoint for completion.

Covered here:
- accept-then-complete: immediate acceptance body, then completion visible
  via API status polling, with EXIF GPS/bearing data extracted
- error propagation: a processing failure in the background task still
  reaches the API and surfaces as processing_status='error' when polling
- auth/validation: invalid upload JWT is rejected with 401, missing
  client_signature form field with 422

Queue-full (503) behavior for /upload_async is covered separately in
test_worker_backpressure.py.
"""

import os
import sys

import httpx
import pytest

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.image_utils import create_test_image_full_gps, create_test_image_no_exif
from utils.secure_upload_utils import SecureUploadClient, generate_test_captured_at
from utils.test_utils import API_URL, wait_for_photo_processing

WORKER_URL = os.getenv("TEST_WORKER_URL", "http://localhost:8056")


async def post_upload_async(upload_client, image_data: bytes, auth_data: dict,
							client_keys: dict, filename: str) -> httpx.Response:
	"""POST directly to the worker's /upload_async with a valid client signature.

	SecureUploadClient.upload_to_worker targets the sync /upload endpoint, so
	the async endpoint's contract (immediate {'success': True}) is asserted on
	the raw response here instead.
	"""
	client_signature = upload_client.generate_client_signature(
		client_keys["private_key"],
		auth_data["photo_id"],
		filename,
		auth_data["upload_authorized_at"]
	)
	async with httpx.AsyncClient() as client:
		return await client.post(
			f"{auth_data['worker_url']}/upload_async",
			files={'file': (filename, image_data, 'image/jpeg')},
			data={'client_signature': client_signature},
			headers={'Authorization': f"Bearer {auth_data['upload_jwt']}"},
			timeout=60.0
		)


class TestUploadAsync(BasePhotoTest):
	"""Async upload endpoint: immediate acceptance + background processing."""

	async def _authorize(self, upload_client, client_keys, filename: str, image_data: bytes) -> dict:
		"""Register the client key and authorize an upload for image_data."""
		await upload_client.register_client_key(self.test_token, client_keys)
		return await upload_client.authorize_upload_with_params(
			self.test_token, filename, len(image_data), 50.0755, 14.4378,
			"Async upload integration test", True, file_data=image_data,
			captured_at=generate_test_captured_at()
		)

	@pytest.mark.asyncio
	async def test_upload_async_accepts_and_completes(self):
		"""A valid async upload is accepted immediately with a bare
		{'success': True} (no processing result in the body), and the photo
		later reaches 'completed' with EXIF GPS data via status polling."""
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()

		filename = "async_upload_test.jpg"
		image_data = create_test_image_full_gps(200, 150, (255, 0, 0), 50.0755, 14.4378, 90.0)
		auth_data = await self._authorize(upload_client, client_keys, filename, image_data)

		response = await post_upload_async(upload_client, image_data, auth_data, client_keys, filename)

		assert response.status_code == 200, f"Async upload rejected: {response.status_code} - {response.text}"
		# The async endpoint acknowledges acceptance only — the processing
		# result (sizes, EXIF, detections) must NOT be in this response,
		# that's what distinguishes it from the sync /upload contract.
		assert response.json() == {"success": True}

		photo = wait_for_photo_processing(auth_data["photo_id"], self.test_token, timeout=60)
		assert photo["processing_status"] == "completed", f"Expected completed, got {photo['processing_status']} (error: {photo.get('error')})"
		assert photo.get("error") is None
		assert photo.get("latitude") is not None, "Expected latitude extracted from EXIF"
		assert photo.get("longitude") is not None, "Expected longitude extracted from EXIF"
		assert photo.get("bearing") is not None, "Expected bearing extracted from EXIF"

	@pytest.mark.asyncio
	async def test_upload_async_error_surfaces_via_polling(self):
		"""A photo that fails processing (no EXIF data) is still accepted with
		{'success': True}; the background task must report the failure to the
		API so polling clients see processing_status='error' with a message."""
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()

		filename = "async_upload_no_exif.jpg"
		image_data = create_test_image_no_exif(color=(0, 0, 255))
		auth_data = await self._authorize(upload_client, client_keys, filename, image_data)

		response = await post_upload_async(upload_client, image_data, auth_data, client_keys, filename)

		assert response.status_code == 200, f"Async upload rejected: {response.status_code} - {response.text}"
		assert response.json() == {"success": True}

		photo = wait_for_photo_processing(auth_data["photo_id"], self.test_token, timeout=60)
		assert photo["processing_status"] == "error", f"Expected error, got {photo['processing_status']}"
		assert "No EXIF data found" in (photo.get("error") or ""), f"Expected EXIF error message, got: {photo.get('error')}"

	@pytest.mark.asyncio
	async def test_upload_async_rejects_invalid_jwt(self):
		"""An invalid upload authorization JWT is rejected with 401 before any
		background task is queued."""
		image_data = create_test_image_full_gps(200, 150, (0, 255, 0), 50.0755, 14.4378, 45.0)
		async with httpx.AsyncClient() as client:
			response = await client.post(
				f"{WORKER_URL}/upload_async",
				files={'file': ('async_bad_jwt.jpg', image_data, 'image/jpeg')},
				data={'client_signature': 'irrelevant-rejected-before-auth'},
				headers={'Authorization': 'Bearer invalid.jwt.token'},
				timeout=60.0
			)
		assert response.status_code == 401, f"Expected 401, got {response.status_code} - {response.text}"

	@pytest.mark.asyncio
	async def test_upload_async_missing_signature_rejected(self):
		"""A request without the client_signature form field fails validation
		(422) instead of being accepted into the queue."""
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()

		filename = "async_missing_sig.jpg"
		image_data = create_test_image_full_gps(200, 150, (255, 255, 0), 50.0755, 14.4378, 45.0)
		auth_data = await self._authorize(upload_client, client_keys, filename, image_data)

		async with httpx.AsyncClient() as client:
			response = await client.post(
				f"{auth_data['worker_url']}/upload_async",
				files={'file': (filename, image_data, 'image/jpeg')},
				headers={'Authorization': f"Bearer {auth_data['upload_jwt']}"},
				timeout=60.0
			)
		assert response.status_code == 422, f"Expected 422, got {response.status_code} - {response.text}"


if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s", "--tb=short"])
