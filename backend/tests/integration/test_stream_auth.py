#!/usr/bin/env python3
"""
Client-signed stream-credential auth tests (auth-review #5).

SSE streams can't send an Authorization header, so instead of putting the full
access token in the URL (which leaks into logs/history), the client signs a short-
TTL, stream-scoped assertion `[key_id, "stream", exp]` with its registered ECDSA key.
The server verifies it via the same `verify_ecdsa_signature` path used for uploads.

These sign with a real P-256 key from Python's `cryptography` (DER signatures, which
the verifier converts), register the public key like a real client, and assert
resolution via `GET /api/debug/whoami-query` (which uses the same optional-auth
dependency the SSE endpoints use). Legacy `?token=` must keep working (rollout compat).
"""
import base64
import json
import os
import sys
import uuid

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.test_utils import recreate_test_users, API_URL
from utils.auth_utils import TEST_CREDENTIALS

WHOAMI = f"{API_URL}/debug/whoami-query"


def _login(username: str = "test") -> dict:
    r = requests.post(
        f"{API_URL}/auth/token",
        data={"username": username, "password": TEST_CREDENTIALS[username]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()


def _register_key(access_token: str):
    """Generate a P-256 keypair, register the public key, return (key_id, private_key)."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    key_id = f"test-stream-key-{uuid.uuid4()}"

    r = requests.post(
        f"{API_URL}/auth/register-client-key",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"public_key_pem": public_pem, "key_id": key_id, "created_at": "2026-01-01T00:00:00Z"},
    )
    assert r.status_code == 200, f"key registration failed: {r.status_code} {r.text}"
    return key_id, private_key


def _sign_stream(private_key, key_id: str, exp: int) -> str:
    """Sign the canonical [key_id, "stream", exp] list the server reconstructs."""
    message = json.dumps([key_id, "stream", exp], separators=(",", ":"),
                         ensure_ascii=False, sort_keys=True).encode("utf-8")
    sig = private_key.sign(message, ec.ECDSA(hashes.SHA256()))  # DER; verifier handles it
    return base64.b64encode(sig).decode()


def _now() -> int:
    # Server compares against int(utcnow().timestamp()); mirror that here.
    import time
    return int(time.time())


def setup_module(module):
    recreate_test_users()


def test_whoami_anonymous_without_credential():
    """No credential → anonymous (baseline; also confirms the debug surface exists)."""
    r = requests.get(WHOAMI)
    assert r.status_code == 200, f"whoami should be reachable (DEBUG_ENDPOINTS on): {r.status_code} {r.text}"
    assert r.json() == {"authenticated": False}


def test_valid_stream_credential_authenticates():
    tokens = _login()
    me = requests.get(f"{API_URL}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()

    key_id, priv = _register_key(tokens["access_token"])
    exp = _now() + 600  # 10 minutes
    sig = _sign_stream(priv, key_id, exp)

    r = requests.get(WHOAMI, params={"stream_key_id": key_id, "stream_exp": exp, "stream_sig": sig})
    assert r.status_code == 200, f"valid stream cred should resolve: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("authenticated") is True, body
    assert body.get("username") == me["username"], body


def test_header_token_still_works():
    """Header bearer auth is unaffected by the stream branch."""
    tokens = _login()
    r = requests.get(WHOAMI, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200 and r.json().get("authenticated") is True, r.text


def test_legacy_query_token_still_works():
    """Old clients put the access token in ?token=; must keep working during rollout."""
    tokens = _login()
    r = requests.get(WHOAMI, params={"token": tokens["access_token"]})
    assert r.status_code == 200 and r.json().get("authenticated") is True, r.text


def test_expired_stream_credential_rejected():
    tokens = _login()
    key_id, priv = _register_key(tokens["access_token"])
    exp = _now() - 60  # already expired
    sig = _sign_stream(priv, key_id, exp)

    r = requests.get(WHOAMI, params={"stream_key_id": key_id, "stream_exp": exp, "stream_sig": sig})
    assert r.status_code == 401, f"expired credential must be rejected: {r.status_code} {r.text}"


def test_far_future_stream_credential_rejected():
    """A signature can't be turned into a long-lived credential (exp cap)."""
    tokens = _login()
    key_id, priv = _register_key(tokens["access_token"])
    exp = _now() + 24 * 3600  # 1 day out, well beyond the 15-min cap
    sig = _sign_stream(priv, key_id, exp)

    r = requests.get(WHOAMI, params={"stream_key_id": key_id, "stream_exp": exp, "stream_sig": sig})
    assert r.status_code == 401, f"far-future credential must be rejected: {r.status_code} {r.text}"


def test_forged_signature_rejected():
    tokens = _login()
    key_id, _priv = _register_key(tokens["access_token"])
    exp = _now() + 600
    # Sign with a DIFFERENT key than the one registered under key_id.
    attacker = ec.generate_private_key(ec.SECP256R1())
    sig = _sign_stream(attacker, key_id, exp)

    r = requests.get(WHOAMI, params={"stream_key_id": key_id, "stream_exp": exp, "stream_sig": sig})
    assert r.status_code == 401, f"forged signature must be rejected: {r.status_code} {r.text}"


def test_tampered_exp_rejected():
    """Extending exp after signing must invalidate the signature."""
    tokens = _login()
    key_id, priv = _register_key(tokens["access_token"])
    exp = _now() + 600
    sig = _sign_stream(priv, key_id, exp)

    r = requests.get(WHOAMI, params={"stream_key_id": key_id, "stream_exp": exp + 300, "stream_sig": sig})
    assert r.status_code == 401, f"tampered exp must be rejected: {r.status_code} {r.text}"


def test_unknown_key_id_rejected():
    exp = _now() + 600
    priv = ec.generate_private_key(ec.SECP256R1())
    key_id = f"never-registered-{uuid.uuid4()}"
    sig = _sign_stream(priv, key_id, exp)

    r = requests.get(WHOAMI, params={"stream_key_id": key_id, "stream_exp": exp, "stream_sig": sig})
    assert r.status_code == 401, f"unknown key_id must be rejected: {r.status_code} {r.text}"
