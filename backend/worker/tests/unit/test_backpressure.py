"""Unit tests for upload queue backpressure (UploadBackpressureMiddleware + /ready)."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# app.py mkdirs UPLOAD_DIR at import time; default /app/uploads only exists in docker
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="hillview-test-uploads-"))

import app as worker_app


@pytest.fixture
def client():
	with TestClient(worker_app.app) as c:
		yield c


@pytest.fixture
def full_queue(monkeypatch):
	"""Make the pending task queue appear at capacity."""
	monkeypatch.setattr(worker_app, "MAX_PENDING_TASKS", 2)
	with worker_app.pending_background_tasks_mutex:
		worker_app.pending_background_tasks.update({"fake_1", "fake_2"})
	yield
	with worker_app.pending_background_tasks_mutex:
		worker_app.pending_background_tasks.discard("fake_1")
		worker_app.pending_background_tasks.discard("fake_2")


class TestReadyEndpoint:
	def test_ready_when_queue_empty(self, client):
		response = client.get("/ready")
		assert response.status_code == 200
		body = response.json()
		assert body["status"] == "ready"
		assert body["pending_tasks"] == 0

	def test_busy_when_queue_full(self, client, full_queue):
		response = client.get("/ready")
		assert response.status_code == 503
		body = response.json()
		assert body["status"] == "busy"
		assert body["pending_tasks"] == 2
		assert response.headers["retry-after"] == str(worker_app.QUEUE_FULL_RETRY_AFTER_SECONDS)


class TestUploadBackpressure:
	def test_upload_rejected_when_queue_full(self, client, full_queue):
		for endpoint in ("/upload", "/upload_async"):
			response = client.post(endpoint, files={"file": ("t.jpg", b"x", "image/jpeg")})
			assert response.status_code == 503, endpoint
			body = response.json()
			assert body["detail"] == "worker_queue_full"
			assert body["pending_tasks"] == 2
			assert response.headers["retry-after"] == str(worker_app.QUEUE_FULL_RETRY_AFTER_SECONDS)

	def test_upload_passes_middleware_when_queue_has_room(self, client):
		# Without auth the endpoint itself rejects with 401/403 —
		# the point is that the middleware (503) did not fire.
		response = client.post("/upload", files={"file": ("t.jpg", b"x", "image/jpeg")})
		assert response.status_code in (401, 403)

	def test_non_upload_paths_unaffected_by_full_queue(self, client, full_queue):
		response = client.get("/health")
		assert response.status_code == 200
