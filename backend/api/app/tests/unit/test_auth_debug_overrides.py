#!/usr/bin/env python3
"""Unit tests for the in-memory auth debug overrides and their test-state reset.

Covers set/get/clear round-trips for the access-TTL and force-logout overrides,
plus reset_debug_overrides() — the belt-and-suspenders wipe called from
recreate-test-users / clear-database so a crashed spec can't leak an override
into the next run.
"""
import os
import sys

# Add api/app to path so we can import the auth module, and backend root for common.
api_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(api_app_dir))
backend_dir = os.path.join(api_app_dir, '..', '..')
sys.path.insert(1, os.path.abspath(backend_dir))

import pytest

import auth


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Each test starts and ends with a clean override state (process-global)."""
    auth.reset_debug_overrides()
    yield
    auth.reset_debug_overrides()


def test_access_ttl_override_round_trip():
    assert auth.get_user_access_ttl("u1") is None
    auth.set_user_access_ttl("u1", 130.0)
    assert auth.get_user_access_ttl("u1") == 130.0
    auth.clear_user_access_ttl("u1")
    assert auth.get_user_access_ttl("u1") is None


def test_force_logout_round_trip():
    assert auth.is_user_force_logged_out("u1") is False
    auth.force_user_logout("u1")
    assert auth.is_user_force_logged_out("u1") is True
    auth.clear_user_force_logout("u1")
    assert auth.is_user_force_logged_out("u1") is False


def test_user_ids_are_stringified():
    # Callers pass UUID objects; keys must normalize so lookups match regardless of type.
    auth.set_user_access_ttl(123, 5.0)
    assert auth.get_user_access_ttl("123") == 5.0
    auth.force_user_logout(123)
    assert auth.is_user_force_logged_out("123") is True


def test_reset_debug_overrides_clears_everything():
    auth.set_user_access_ttl("u1", 130.0)
    auth.set_user_access_ttl("u2", 45.0)
    auth.force_user_logout("u3")

    auth.reset_debug_overrides()

    assert auth.get_user_access_ttl("u1") is None
    assert auth.get_user_access_ttl("u2") is None
    assert auth.is_user_force_logged_out("u3") is False


def test_reset_debug_overrides_is_idempotent_on_empty_state():
    # Must be safe to call when nothing was ever set (the common wipe case).
    auth.reset_debug_overrides()
    auth.reset_debug_overrides()
    assert auth.get_user_access_ttl("nobody") is None
    assert auth.is_user_force_logged_out("nobody") is False
