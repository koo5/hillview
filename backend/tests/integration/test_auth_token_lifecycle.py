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
from typing import Optional

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


# ---------------------------------------------------------------------------
# SSR read ticket — the third token in the payload. Read-only by construction:
# accepted by the handful of read endpoints the web frontend's server renderer
# calls, rejected everywhere else. See docs/ssr-auth-ticket.md.
# ---------------------------------------------------------------------------

def _bestof(bearer: Optional[str]) -> requests.Response:
    """One of the SSR read endpoints, called the way the server renderer does."""
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return requests.get(f"{API_URL}/bestof/photos", headers=headers)


def _tampered(token: str) -> str:
    """
    Same header and claims, signature no longer matching — what a ticket signed
    with a rotated key looks like to the API. The FIRST signature character is
    changed: the last one may carry unused padding bits, which a flip would not
    disturb.
    """
    head, body, sig = token.split(".")
    return f"{head}.{body}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"


def test_login_and_refresh_issue_an_ssr_ticket():
    """Both token-issuing responses carry a ticket, and refresh rotates it."""
    tokens = _login()
    assert tokens.get("ssr_token") and tokens.get("ssr_token_expires_at"), \
        "login must return the SSR ticket and its expiry"

    refreshed = _refresh(tokens["refresh_token"]).json()
    assert refreshed.get("ssr_token") and refreshed["ssr_token"] != tokens["ssr_token"], \
        "refresh must issue a fresh ticket"


def test_ssr_ticket_renders_the_visitors_own_view():
    """A read endpoint SSR calls accepts the ticket and says who the batch is for."""
    tokens = _login()
    me = _me(tokens["access_token"]).json()

    resp = _bestof(tokens["ssr_token"])
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
    assert resp.json().get("viewer_id") == me["id"], "batch must be tagged with the ticket's user"

    anonymous = _bestof(None)
    assert anonymous.status_code == 200
    assert anonymous.json().get("viewer_id") is None, "an anonymous batch says so"


def test_ssr_ticket_is_not_a_credential_elsewhere():
    """
    The ticket must authenticate nothing outside the SSR read endpoints: not a
    protected read, not a write, and it must not be laundered into a session
    through /auth/refresh. This is the property that makes a cookie holding it
    acceptable.
    """
    tokens = _login()
    ticket = tokens["ssr_token"]

    assert _me(ticket).status_code == 401, "ticket must not pass get_current_user"
    assert _logout(ticket).status_code == 401, "ticket must not authenticate a write"
    assert _refresh(ticket).status_code == 401, "ticket must not act as a refresh token"


def test_ssr_ticket_dies_with_the_session():
    """Logout revokes the session family; the ticket then renders anonymously."""
    tokens = _login()
    assert _logout(tokens["access_token"]).status_code == 200

    resp = _bestof(tokens["ssr_token"])
    assert resp.status_code == 200, "a revoked ticket degrades, it does not error"
    assert resp.json().get("viewer_id") is None


def test_invalid_ssr_ticket_degrades_to_anonymous_not_401():
    """
    A ticket that fails validation — expired, or signed with a rotated key — must
    produce the anonymous render, not a 401 the photo page turns into an error
    page. The cookie can outlive its ticket (client clock behind the server), so
    this is a real path, not a hypothetical.

    An invalid *access* token on the same endpoint stays a 401: the strict
    contract for real credentials is untouched.
    """
    tokens = _login()

    resp = _bestof(_tampered(tokens["ssr_token"]))
    assert resp.status_code == 200, f"dead ticket must render anonymously — got {resp.status_code}: {resp.text}"
    assert resp.json().get("viewer_id") is None

    assert _bestof(_tampered(tokens["access_token"])).status_code == 401, \
        "an invalid access token must still be a 401 on the same endpoint"


def _annotations(bearer: Optional[str]) -> requests.Response:
    """The other SSR read endpoint, and the forgiving one.

    Its photo id need not exist: what is under test is which credentials the
    endpoint accepts, not what it finds.
    """
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return requests.get(f"{API_URL}/annotations/photos/no-such-photo", headers=headers)


def test_the_two_ssr_dependencies_keep_their_own_manners():
    """
    Both SSR read dependencies accept the ticket, and each keeps the failure mode
    its endpoints already had for a bad ACCESS token: bestof answers 401, the
    annotation listing shrugs and serves the anonymous view.

    The second half is the compatibility promise. Annotation listing has always
    been forgiving, so an installed app whose access token expired keeps seeing
    annotations. Moving it to the strict flavour would have turned that into an
    error, silently, on devices nobody can redeploy.
    """
    tokens = _login()

    assert _annotations(tokens["ssr_token"]).status_code == 200, "ticket must be accepted here too"
    assert _annotations(_tampered(tokens["access_token"])).status_code == 200, \
        "a bad access token must still degrade to anonymous on the forgiving endpoint"
    assert _bestof(_tampered(tokens["access_token"])).status_code == 401, \
        "and must still be a 401 on the strict one"


def test_anonymous_reads_are_tagged_as_belonging_to_nobody():
    """
    `viewer_id` is what the page compares against the signed-in user to decide
    whether to refetch (createSsrBackedLoad). Null for an anonymous caller is the
    half that keeps a crawler's render from being adopted by a signed-in visitor,
    so it is asserted on every endpoint that reports it, not just the one.
    """
    assert _bestof(None).json().get("viewer_id") is None
    assert requests.get(f"{API_URL}/activity/recent?limit=1").json().get("viewer_id") is None


def test_ssr_ticket_tags_activity_with_its_user_too():
    """The ticket resolves the same on /activity/recent as on /bestof/photos."""
    tokens = _login()
    me = _me(tokens["access_token"]).json()

    resp = requests.get(
        f"{API_URL}/activity/recent?limit=1",
        headers={"Authorization": f"Bearer {tokens['ssr_token']}"},
    )
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
    assert resp.json().get("viewer_id") == me["id"]
