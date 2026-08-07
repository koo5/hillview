"""POST /auth/google/native — the Credential Manager login door.

Unit-level: Google's JWKS never gets hit (the verify seam is patched) and
the DB tail is stubbed — oauth_user_to_tokens itself is the verbatim
extraction of the OAuth callback tail, already covered by the OAuth
integration tests. What's under test is the door's own logic: config
gating, token-shape bounds, claim requirements, and that a verified
identity is handed to the shared tail exactly once.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore", message="The 'app' shortcut is now deprecated", category=DeprecationWarning)

# The user-routes router only mounts under USER_ACCOUNTS — must be set
# before `import api` (same as every auth unit test here).
os.environ["USER_ACCOUNTS"] = "true"

# Add the parent directory (api/app) to path so we can import the API modules
api_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(api_app_dir))

backend_dir = os.path.join(api_app_dir, '..', '..')
sys.path.insert(0, os.path.abspath(backend_dir))

import pytest
from fastapi.testclient import TestClient

import api
import auth
import user_routes
from common.database import get_db

app = api.app


class _StubSession:
	"""Just enough session for security_audit.log_event (which swallows
	its own errors anyway) — the token tail is patched out in these tests."""

	def add(self, obj):
		pass

	async def commit(self):
		pass

	async def rollback(self):
		pass

	async def close(self):
		pass


async def _stub_get_db():
	yield _StubSession()


@pytest.fixture()
def client(monkeypatch):
	monkeypatch.setitem(auth.OAUTH_PROVIDERS["google"], "client_id", "test-client-id")
	app.dependency_overrides[get_db] = _stub_get_db
	try:
		yield TestClient(app)
	finally:
		app.dependency_overrides.pop(get_db, None)


GOOD_CLAIMS = {"sub": "google-uid-1", "email": "native@example.com", "email_verified": True}


def test_unconfigured_google_is_a_503(client, monkeypatch):
	monkeypatch.setitem(auth.OAUTH_PROVIDERS["google"], "client_id", "")
	r = client.post("/api/auth/google/native", json={"id_token": "x" * 40})
	assert r.status_code == 503


def test_failed_verification_is_a_400(client, monkeypatch):
	def boom(token):
		raise ValueError("bad signature")
	monkeypatch.setattr(user_routes, "verify_google_id_token", boom)
	r = client.post("/api/auth/google/native", json={"id_token": "x" * 40})
	assert r.status_code == 400
	assert "Invalid Google ID token" in r.text


def test_oversized_token_never_reaches_the_verifier(client, monkeypatch):
	def must_not_run(token):
		raise AssertionError("verifier must not be called")
	monkeypatch.setattr(user_routes, "verify_google_id_token", must_not_run)
	r = client.post("/api/auth/google/native", json={"id_token": "x" * 5000})
	assert r.status_code == 400


def test_missing_sub_or_email_is_a_400(client, monkeypatch):
	monkeypatch.setattr(
		user_routes, "verify_google_id_token", lambda t: {"email": "no-sub@example.com"}
	)
	r = client.post("/api/auth/google/native", json={"id_token": "x" * 40})
	assert r.status_code == 400
	assert "required claims" in r.text


def test_unverified_email_is_rejected(client, monkeypatch):
	# An unverified address must not capture the account that owns that
	# email (the shared tail matches on it).
	claims = dict(GOOD_CLAIMS, email_verified=False)
	monkeypatch.setattr(user_routes, "verify_google_id_token", lambda t: claims)
	r = client.post("/api/auth/google/native", json={"id_token": "x" * 40})
	assert r.status_code == 400
	assert "not verified" in r.text


def test_verified_identity_reaches_the_shared_tail_and_returns_its_tokens(client, monkeypatch):
	monkeypatch.setattr(user_routes, "verify_google_id_token", lambda t: dict(GOOD_CLAIMS))

	calls = []

	async def fake_tail(db, provider, oauth_id, email):
		calls.append((provider, oauth_id, email))
		return {
			"access_token": "at",
			"refresh_token": "rt",
			"token_type": "bearer",
			"expires_at": "2099-01-01T00:00:00Z",
			"refresh_token_expires_at": "2099-02-01T00:00:00Z",
			"user_info": {"user_id": "u1", "username": "native", "role": "user"},
		}

	monkeypatch.setattr(user_routes, "oauth_user_to_tokens", fake_tail)

	r = client.post("/api/auth/google/native", json={"id_token": "x" * 40})
	assert r.status_code == 200
	body = r.json()
	assert body["access_token"] == "at"
	assert body["refresh_token"] == "rt"
	assert calls == [("google", "google-uid-1", "native@example.com")]
