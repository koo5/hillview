"""Unit tests for the shared HTTP fault-injection matcher (common.debug_faults).

Covers the chaos-monkey logic used by both the API and worker middleware:
glob matching, status, per-request count, method restriction, snapshot, and the
prod safety gate. The middleware/web wiring (install()) is exercised via the
service apps, not here.
"""
import pytest

from common import debug_faults


@pytest.fixture(autouse=True)
def enabled_and_clean(monkeypatch):
    # Fault injection is DEV_MODE-only (faults_enabled) — enable it for the matcher
    # tests. DEBUG_ENDPOINTS deliberately does NOT enable it (see the test below).
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.delenv("DEBUG_ENDPOINTS", raising=False)
    debug_faults.clear()
    yield
    debug_faults.clear()


def test_no_fault_when_nothing_armed():
    assert debug_faults.match("GET", "/api/auth/me") is None


def test_glob_match_returns_configured_status():
    debug_faults.arm("/api/auth/*", status=500)
    fault = debug_faults.match("GET", "/api/auth/me")
    assert fault is not None
    assert fault.status == 500


def test_non_matching_path_is_untouched():
    debug_faults.arm("/api/auth/*", status=500)
    assert debug_faults.match("GET", "/api/photos") is None


def test_count_is_consumed_then_stops():
    debug_faults.arm("/x", count=2)
    assert debug_faults.match("GET", "/x") is not None
    assert debug_faults.match("GET", "/x") is not None
    assert debug_faults.match("GET", "/x") is None  # exhausted


def test_until_cleared_keeps_matching():
    debug_faults.arm("/x")  # count=None → until cleared
    for _ in range(5):
        assert debug_faults.match("GET", "/x") is not None


def test_method_restriction():
    debug_faults.arm("/x", methods=["POST"])
    assert debug_faults.match("GET", "/x") is None
    assert debug_faults.match("POST", "/x") is not None


def test_clear_removes_all_faults():
    debug_faults.arm("/x")
    debug_faults.clear()
    assert debug_faults.snapshot() == []
    assert debug_faults.match("GET", "/x") is None


def test_snapshot_reports_armed_faults():
    debug_faults.arm("/api/auth/me", status=500, count=3, delay_seconds=1.5)
    snap = debug_faults.snapshot()
    assert len(snap) == 1
    assert snap[0]["path"] == "/api/auth/me"
    assert snap[0]["status"] == 500
    assert snap[0]["remaining"] == 3
    assert snap[0]["delay_seconds"] == 1.5


def test_inert_when_debug_flags_disabled(monkeypatch):
    monkeypatch.delenv("DEBUG_ENDPOINTS", raising=False)
    monkeypatch.delenv("DEV_MODE", raising=False)
    debug_faults.arm("/x")  # armed, but injection must be inert without the flag
    assert debug_faults.match("GET", "/x") is None


def test_enabled_via_dev_mode(monkeypatch):
    monkeypatch.delenv("DEBUG_ENDPOINTS", raising=False)
    monkeypatch.setenv("DEV_MODE", "1")
    debug_faults.arm("/x")
    assert debug_faults.match("GET", "/x") is not None


def test_debug_endpoints_alone_does_NOT_enable_faults(monkeypatch):
    # Fault injection is intentionally stricter than the read-only debug endpoints:
    # DEBUG_ENDPOINTS may be on in a staging-ish env, but must never let a fault break
    # a live request. Only DEV_MODE does. (faults_enabled vs is_enabled.)
    monkeypatch.setenv("DEBUG_ENDPOINTS", "true")
    monkeypatch.delenv("DEV_MODE", raising=False)
    assert debug_faults.is_enabled() is True       # broad debug gate is on
    assert debug_faults.faults_enabled() is False  # but fault injection is not
    debug_faults.arm("/x")
    assert debug_faults.match("GET", "/x") is None
