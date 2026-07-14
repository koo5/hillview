"""Unit tests for upload queue backpressure (UploadBackpressureMiddleware + /ready)."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# app.py mkdirs UPLOAD_DIR at import time; default /app/uploads only exists in docker
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="hillview-test-uploads-"))

import app as worker_app


@pytest.fixture(autouse=True)
def _no_worker_pool(monkeypatch):
	"""Don't spawn the real worker child: its spawn-time warm-up imports
	cv2/torch (tens of seconds), and these tests exercise HTTP surfaces only."""
	monkeypatch.setattr(worker_app.worker_processing, "start", lambda *a, **k: None)
	monkeypatch.setattr(worker_app.worker_processing, "shutdown", lambda: None)


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
		# machine id is always in the body so clients can pin uploads to the
		# machine that answered ready (fly-force-instance-id request header)
		assert "fly_machine_id" in body

	def test_busy_when_queue_full(self, client, full_queue):
		response = client.get("/ready")
		assert response.status_code == 503
		body = response.json()
		assert body["status"] == "busy"
		assert body["pending_tasks"] == 2
		assert "fly_machine_id" in body
		assert response.headers["retry-after"] == str(worker_app.QUEUE_FULL_RETRY_AFTER_SECONDS)
		# busy asks the Fly edge to re-run the preflight on a sibling machine
		assert response.headers["fly-replay"] == "elsewhere=true"

	def test_busy_replay_kill_switch(self, client, full_queue, monkeypatch):
		"""READY_FLY_REPLAY=false suppresses the steering header — the escape
		hatch for running a single-machine fleet, where `elsewhere=true` has
		nowhere to go and the proxy strands the request ~35 s (measured live
		2026-07-13) before returning a bare empty-body 503."""
		monkeypatch.setattr(worker_app, "READY_FLY_REPLAY", False)
		response = client.get("/ready")
		assert response.status_code == 503
		assert "fly-replay" not in response.headers
		assert response.json()["status"] == "busy"

	def test_busy_replayed_request_not_replayed_again(self, client, full_queue):
		"""A request already carrying fly-replay-src was replayed once — answer
		plainly so a fully-busy fleet can't loop replays."""
		response = client.get(
			"/ready",
			headers={"fly-replay-src": "instance=d8de7d0b903e68;region=fra;t=1752400000000000"},
		)
		assert response.status_code == 503
		assert "fly-replay" not in response.headers
		assert response.json()["status"] == "busy"

	def test_simulated_busy_any(self, client):
		"""debug_simulate_busy=any fakes the busy path with no state touched."""
		response = client.get("/ready?debug_simulate_busy=any")
		assert response.status_code == 503
		body = response.json()
		assert body["simulated_busy"] is True
		assert body["pending_tasks"] == 0  # real state untouched
		assert response.headers["fly-replay"] == "elsewhere=true"
		# and a plain request is still ready
		assert client.get("/ready").status_code == 200

	def test_simulated_busy_other_machine_ignored(self, client, monkeypatch):
		"""Simulation targeting a different machine id leaves this one ready."""
		monkeypatch.setattr(worker_app, "FLY_MACHINE_ID", "aaaa11112222")
		response = client.get("/ready?debug_simulate_busy=bbbb33334444")
		assert response.status_code == 200
		assert response.json()["fly_machine_id"] == "aaaa11112222"


class TestBoredShutdown:
	"""The _bored_for predicate + which requests count as activity."""

	def test_bored_when_idle_past_threshold(self, monkeypatch):
		monkeypatch.setattr(worker_app, "BORED_SHUTDOWN_SECONDS", 100)
		monkeypatch.setattr(worker_app, "_last_activity", worker_app.time.monotonic() - 200)
		idle = worker_app._bored_for()
		assert idle is not None and idle >= 200

	def test_not_bored_with_recent_activity(self, monkeypatch):
		monkeypatch.setattr(worker_app, "BORED_SHUTDOWN_SECONDS", 100)
		monkeypatch.setattr(worker_app, "_last_activity", worker_app.time.monotonic())
		assert worker_app._bored_for() is None

	def test_not_bored_with_pending_work(self, monkeypatch, full_queue):
		monkeypatch.setattr(worker_app, "BORED_SHUTDOWN_SECONDS", 100)
		monkeypatch.setattr(worker_app, "_last_activity", worker_app.time.monotonic() - 200)
		assert worker_app._bored_for() is None  # full_queue puts 2 fake pending tasks

	def test_not_bored_with_request_in_flight(self, monkeypatch):
		monkeypatch.setattr(worker_app, "BORED_SHUTDOWN_SECONDS", 100)
		monkeypatch.setattr(worker_app, "_last_activity", worker_app.time.monotonic() - 200)
		monkeypatch.setattr(worker_app, "_inflight_requests", 1)
		assert worker_app._bored_for() is None

	def test_noise_paths_do_not_reset_idleness(self, client, monkeypatch):
		"""Health checks / metrics scrapes must not count as activity, or an
		idle machine would never become bored."""
		old = worker_app.time.monotonic() - 500
		monkeypatch.setattr(worker_app, "_last_activity", old)
		client.get("/metrics")
		client.get("/servicecheck")
		assert worker_app._last_activity == old
		client.get("/ready")  # a real client preflight IS activity
		assert worker_app._last_activity > old


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
