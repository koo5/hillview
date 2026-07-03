#!/usr/bin/env python3
"""
OAuth `state` CSRF-protection tests.

The OAuth `state` must be a server-issued, one-time nonce: the callback has to
reject any state the server didn't just hand out, and accept a real one only once.
Without that, an attacker can craft/replay a callback (login CSRF — logging a victim
into the attacker's account, or replaying a captured code+state).

These talk to the live API. They deliberately avoid depending on a real provider
token exchange (no creds / outbound network assumed): the state check happens BEFORE
any code exchange, so a forged state is rejected on its own, and the one-time
property is asserted via a replay that must fail as invalid-state regardless of what
the first use did.
"""
import os
import sys
from urllib.parse import urlparse, parse_qs

import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.test_utils import API_URL


def _detail(resp) -> str:
    try:
        return str(resp.json().get("detail", "")).lower()
    except Exception:
        return ""


def _is_state_rejection(resp) -> bool:
    return resp.status_code == 400 and "state" in _detail(resp)


def _issue_state(provider: str = "google", redirect_uri: str = "cz.hillview://auth") -> str:
    """Drive /auth/oauth-redirect and pull the server-issued state nonce out of the
    provider URL it redirects to."""
    r = requests.get(
        f"{API_URL}/auth/oauth-redirect",
        params={"provider": provider, "redirect_uri": redirect_uri},
        allow_redirects=False,
    )
    assert r.status_code in (302, 307), f"redirect expected, got {r.status_code}: {r.text}"
    location = r.headers["location"]
    state = parse_qs(urlparse(location).query).get("state", [None])[0]
    assert state, f"no state in provider redirect URL: {location}"
    return state


def test_backend_callback_rejects_unissued_state():
    """A state the server never issued must be rejected outright at /auth/oauth-callback."""
    resp = requests.get(
        f"{API_URL}/auth/oauth-callback",
        params={"code": "irrelevant", "state": "forged-state-not-issued-by-server"},
        allow_redirects=False,
    )
    assert _is_state_rejection(resp), \
        f"forged state must be rejected as invalid — got {resp.status_code}: {resp.text}"


def test_backend_callback_state_is_one_time():
    """A genuine issued state passes the state check once; replaying it is rejected."""
    state = _issue_state()

    # First use gets PAST the state check. It then fails at the (fake) code exchange,
    # which may be a 400 or, with no outbound network, a 500 — either way it must NOT
    # be the invalid-state rejection.
    first = requests.get(
        f"{API_URL}/auth/oauth-callback",
        params={"code": "fake-code", "state": state},
        allow_redirects=False,
    )
    assert not _is_state_rejection(first), \
        f"a freshly issued state must pass the state check — got {first.status_code}: {first.text}"

    # Replay: the nonce was consumed, so this must now be rejected as invalid state.
    replay = requests.get(
        f"{API_URL}/auth/oauth-callback",
        params={"code": "fake-code", "state": state},
        allow_redirects=False,
    )
    assert _is_state_rejection(replay), \
        f"replayed (consumed) state must be rejected — got {replay.status_code}: {replay.text}"


def test_web_oauth_post_rejects_forged_state():
    """The web exchange endpoint (POST /auth/oauth) must also reject a forged state
    before attempting any code exchange."""
    resp = requests.post(
        f"{API_URL}/auth/oauth",
        json={
            "code": "irrelevant",
            "state": "forged-state-not-issued-by-server",
            "redirect_uri": "http://localhost:8212/oauth/callback",
        },
    )
    assert _is_state_rejection(resp), \
        f"forged state on POST /auth/oauth must be rejected — got {resp.status_code}: {resp.text}"
