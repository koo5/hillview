#!/usr/bin/env python3
"""
Auth token lifecycle / "chaos monkey" security tests.

These exercise server-side session revocation and refresh-token hygiene — the
areas an access-token-only blacklist tends to get wrong:

  * logout must revoke the *refresh* token, not just the access token, or a
    leaked/held refresh token keeps minting access tokens for its full lifetime;
  * a rotated refresh token must be single-use, or rotation provides no replay
    protection (a captured old refresh token stays valid).

They talk to the live API (API_URL) exactly like a real client, so they cover
the full validate -> blacklist -> DB path, not a mocked slice of it.
"""
import os
import sys

import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.test_utils import recreate_test_users, API_URL
from utils.auth_utils import TEST_CREDENTIALS


def _login(username: str = "test") -> dict:
    """Password-login and return the full token payload."""
    resp = requests.post(
        f"{API_URL}/auth/token",
        data={"username": username, "password": TEST_CREDENTIALS[username]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("access_token") and data.get("refresh_token"), "login must return both tokens"
    return data


def _refresh(refresh_token: str) -> requests.Response:
    return requests.post(
        f"{API_URL}/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"Content-Type": "application/json"},
    )


def _me(access_token: str) -> requests.Response:
    return requests.get(
        f"{API_URL}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def _logout(access_token: str) -> requests.Response:
    return requests.post(
        f"{API_URL}/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def setup_module(module):
    recreate_test_users()


# ---------------------------------------------------------------------------
# Baselines — these should hold with or without the hardening.
# ---------------------------------------------------------------------------

def test_login_then_authenticated_request_works():
    """A fresh access token is accepted by a protected endpoint."""
    tokens = _login()
    assert _me(tokens["access_token"]).status_code == 200


def test_refresh_returns_working_access_token():
    """Refresh yields a usable access token and rotates the refresh token."""
    tokens = _login()
    resp = _refresh(tokens["refresh_token"])
    assert resp.status_code == 200, f"refresh failed: {resp.status_code} {resp.text}"
    new = resp.json()
    assert new["access_token"] != tokens["access_token"], "refresh must issue a new access token"
    assert new.get("refresh_token") and new["refresh_token"] != tokens["refresh_token"], \
        "refresh must rotate the refresh token"
    assert _me(new["access_token"]).status_code == 200


def test_logout_blacklists_access_token():
    """After logout the access token used to log out is rejected (blacklist works)."""
    tokens = _login()
    assert _me(tokens["access_token"]).status_code == 200
    assert _logout(tokens["access_token"]).status_code == 200
    assert _me(tokens["access_token"]).status_code == 401, \
        "access token must be rejected after logout"


# ---------------------------------------------------------------------------
# Security assertions — the "chaos monkey" cases.
# ---------------------------------------------------------------------------

def test_logout_revokes_refresh_token():
    """
    Logout must end the whole session: the refresh token must NOT be able to
    mint a new access token afterwards.

    Regression guard for the logout-bypass where /auth/logout blacklists only
    the access token and /auth/refresh never consults the blacklist.
    """
    tokens = _login()
    assert _logout(tokens["access_token"]).status_code == 200

    resp = _refresh(tokens["refresh_token"])
    assert resp.status_code == 401, (
        "refresh token must be revoked by logout — got "
        f"{resp.status_code}: {resp.text}"
    )


def test_rotated_refresh_token_is_single_use():
    """
    Refresh-token rotation must invalidate the old token: replaying the
    pre-rotation refresh token must fail. Otherwise a captured refresh token is
    a long-lived bearer credential and rotation buys no replay protection.
    """
    tokens = _login()

    first = _refresh(tokens["refresh_token"])
    assert first.status_code == 200, f"first refresh failed: {first.status_code} {first.text}"

    replay = _refresh(tokens["refresh_token"])  # reuse the ORIGINAL refresh token
    assert replay.status_code == 401, (
        "reusing a rotated refresh token must be rejected — got "
        f"{replay.status_code}: {replay.text}"
    )


def test_logout_revokes_sibling_access_token_via_family():
    """
    Logout must kill the *whole* session family, not just the one access token
    presented to /auth/logout. After a refresh there are two access tokens from
    the same login (same sid); logging out with the newer one must also reject
    the older one, which was never individually blacklisted.
    """
    tokens = _login()
    access1 = tokens["access_token"]

    refreshed = _refresh(tokens["refresh_token"]).json()
    access2 = refreshed["access_token"]

    # Both siblings work before logout.
    assert _me(access1).status_code == 200
    assert _me(access2).status_code == 200

    assert _logout(access2).status_code == 200

    # The sibling we never logged out with is dead too (family-level revocation).
    assert _me(access1).status_code == 401, \
        "sibling access token from the same login must be rejected after logout"


def test_refresh_token_reuse_revokes_the_session():
    """
    Reuse-detection should be defensive: once an old refresh token is replayed
    (a sign of theft), the newly-issued refresh token from the legitimate
    rotation should also be revoked, forcing a clean re-login.
    """
    tokens = _login()

    first = _refresh(tokens["refresh_token"])
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]

    # Attacker replays the stolen original token.
    replay = _refresh(tokens["refresh_token"])
    assert replay.status_code == 401

    # The legitimate client's rotated token is now also dead.
    after = _refresh(new_refresh)
    assert after.status_code == 401, (
        "detecting refresh-token reuse must revoke the whole token family — got "
        f"{after.status_code}: {after.text}"
    )
