#!/usr/bin/env python3
"""
Worker upload-queue backpressure integration tests.

Exercises the real worker over HTTP:
- /ready readiness endpoint (200 with room, 503 + Retry-After at capacity)
- UploadBackpressureMiddleware rejecting POST /upload* with 503
  worker_queue_full before the multipart body is parsed
- normal upload flow recovering once the cap is restored

Queue-full state is simulated via the worker's DEV_MODE-only
POST /debug/max_pending_tasks?value=0 knob rather than actually filling
the queue (which would need MAX_PENDING_TASKS concurrent slow uploads).
Tests skip when the worker isn't running in DEV_MODE.
"""

import os
import sys

import httpx
import pytest

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseIntegrationTest
from utils.image_utils import create_test_image_full_gps
from utils.secure_upload_utils import SecureUploadClient, generate_test_captured_at
from utils.test_utils import API_URL, wait_for_photo_processing

WORKER_URL = os.getenv("TEST_WORKER_URL", "http://localhost:8056")


async def set_worker_cap(value: int) -> int:
	"""Set MAX_PENDING_TASKS via the worker's DEV_MODE debug knob.

	Returns the previous value so callers can restore it. Skips the test
	when the knob is unavailable (worker not running in DEV_MODE).
	"""
	async with httpx.AsyncClient() as client:
		response = await client.post(
			f"{WORKER_URL}/debug/max_pending_tasks",
			params={"value": value},
			timeout=30.0
		)
	if response.status_code == 404:
		pytest.skip("Worker not running in DEV_MODE — /debug/max_pending_tasks unavailable")
	assert response.status_code == 200, f"Debug knob failed: {response.status_code} - {response.text}"
	return response.json()["old"]


class TestWorkerBackpressure(BaseIntegrationTest):
	"""Queue-full behavior of the worker's upload endpoints and /ready."""

	@pytest.mark.asyncio
	async def test_ready_endpoint_reports_ready(self):
		"""With a non-full queue, /ready returns 200 with a pending count."""
		async with httpx.AsyncClient() as client:
			response = await client.get(f"{WORKER_URL}/ready", timeout=30.0)

		assert response.status_code == 200
		body = response.json()
		assert body["status"] == "ready"
		assert isinstance(body["pending_tasks"], int)

	@pytest.mark.asyncio
	async def test_queue_full_rejects_uploads_then_recovers(self):
		"""Full queue: /ready and /upload* return 503; restoring the cap
		lets the same authorized upload complete end-to-end."""
		token = self.get_test_token()
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(token, client_keys)

		filename = "backpressure_test.jpg"
		image_data = create_test_image_full_gps(200, 150, (255, 0, 0), 50.0755, 14.4378, 45.0)
		auth_data = await upload_client.authorize_upload_with_params(
			token, filename, len(image_data), 50.0755, 14.4378,
			"Backpressure integration test", True, file_data=image_data,
			captured_at=generate_test_captured_at()
		)

		old_cap = await set_worker_cap(0)
		try:
			# /ready flips to busy with a Retry-After hint
			async with httpx.AsyncClient() as client:
				ready = await client.get(f"{WORKER_URL}/ready", timeout=30.0)
			assert ready.status_code == 503
			assert ready.json()["status"] == "busy"
			assert "retry-after" in ready.headers

			# /upload (sync) is rejected by the middleware
			with pytest.raises(Exception) as excinfo:
				await upload_client.upload_to_worker(image_data, auth_data, client_keys, filename)
			assert "503" in str(excinfo.value)
			assert "worker_queue_full" in str(excinfo.value)

			# /upload_async (what JS/Kotlin clients use) is rejected too,
			# with the structured detail clients key off
			async with httpx.AsyncClient() as client:
				response = await client.post(
					f"{WORKER_URL}/upload_async",
					files={'file': (filename, image_data, 'image/jpeg')},
					data={'client_signature': 'irrelevant-rejected-before-auth'},
					headers={'Authorization': f"Bearer {auth_data['upload_jwt']}"},
					timeout=60.0
				)
			assert response.status_code == 503
			body = response.json()
			assert body["detail"] == "worker_queue_full"
			assert "retry-after" in response.headers
		finally:
			await set_worker_cap(old_cap)

		# Cap restored: /ready is ready again and the same authorized
		# upload (untouched 'authorized' photo row) completes end-to-end
		async with httpx.AsyncClient() as client:
			ready = await client.get(f"{WORKER_URL}/ready", timeout=30.0)
		assert ready.status_code == 200

		result = await upload_client.upload_to_worker(image_data, auth_data, client_keys, filename)
		assert result.get("success") is True

		photo = wait_for_photo_processing(auth_data["photo_id"], token, timeout=60)
		assert photo["processing_status"] == "completed"
