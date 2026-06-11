#!/usr/bin/env python3
"""Backend test lock integration tests (tests/lock_util.py + the TS port).

The lock under test is the very one conftest.py's session fixture holds
while THIS suite runs — every test here uses its own per-test API URL, so
it operates on a distinct per-server lock file and never contends with the
session lock.

Covered:
1. lock_path derivation (per-server scoping)
2. shared/exclusive semantics across real processes — SH+SH overlap,
   EX drains SH, SH still granted while EX waits (a test run must wait for
   the whole in-flight upload stream — intended)
3. kernel auto-release on kill -9 (no stale locks by construction)
4. holders() diagnostics from /proc/locks
5. cross-language: frontend/tests-*/helpers/testLock.ts holds the same
   kernel lock (skipped with a visible reason if frontend/node_modules
   isn't installed)
"""

import os
import subprocess
import sys
import time

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import lock_util

TESTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FRONTEND_DIR = os.path.abspath(
    os.path.join(TESTS_DIR, '..', '..', 'frontend'))
TSX = os.path.join(FRONTEND_DIR, 'node_modules', '.bin', 'tsx')
TS_HELPER = os.path.join(
    FRONTEND_DIR, 'tests-playwright', 'helpers', 'testLock.ts')


def _api_url(test_name: str) -> str:
    """Unique fake API URL per test → distinct lock file, no cross-talk
    with the session lock or parallel tests."""
    return f"http://lock-test-{test_name}.invalid:1"


# ---------------------------------------------------------------------------
# 1. per-server path derivation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    (None, None),  # placeholder, handled below (env-dependent default)
    ("http://localhost:8055/api", "/tmp/hillview-test-backend.localhost_8055.lock"),
    ("https://hillview.example/api", "/tmp/hillview-test-backend.hillview.example_443.lock"),
    ("hillview.example:8080", "/tmp/hillview-test-backend.hillview.example_8080.lock"),
    ("http://[::1]:8055/api", "/tmp/hillview-test-backend.__1_8055.lock"),
])
def test_lock_path_derivation(url, expected, monkeypatch):
    if url is None:
        # No explicit URL and no env → DEFAULT_API_URL.
        monkeypatch.delenv("API_URL", raising=False)
        assert lock_util.lock_path() == lock_util.lock_path(lock_util.DEFAULT_API_URL)
        return
    assert lock_util.lock_path(url) == expected


def test_lock_path_env_override(monkeypatch):
    monkeypatch.setenv("API_URL", "http://kozi.example:1234/api")
    assert lock_util.lock_path() == "/tmp/hillview-test-backend.kozi.example_1234.lock"


def test_distinct_servers_do_not_contend():
    a = lock_util.BackendLock(shared=False, api_url=_api_url("distinct-a"))
    b = lock_util.BackendLock(shared=False, api_url=_api_url("distinct-b"))
    with a, b:  # both exclusive, both held at once — different servers
        pass


# ---------------------------------------------------------------------------
# 2.–4. cross-process semantics
# ---------------------------------------------------------------------------

def _spawn_holder(api_url: str, shared: bool, hold_s: float) -> subprocess.Popen:
    """Child process that holds the lock and reports via stdout."""
    code = (
        "import sys, time; sys.path.insert(0, sys.argv[1]); import lock_util\n"
        "lock = lock_util.BackendLock(shared=sys.argv[3] == 'sh', api_url=sys.argv[2])\n"
        "lock.acquire()\n"
        "print('HOLDER_ACQUIRED', flush=True)\n"
        "time.sleep(float(sys.argv[4]))\n"
        "lock.release()\n"
    )
    p = subprocess.Popen(
        [sys.executable, "-u", "-c", code, TESTS_DIR, api_url,
         "sh" if shared else "ex", str(hold_s)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 10
    for line in p.stdout:
        if "HOLDER_ACQUIRED" in line:
            return p
        if time.monotonic() > deadline:
            break
    p.kill()
    raise RuntimeError("holder child never acquired")


def _timed_acquire(api_url: str, shared: bool) -> float:
    t0 = time.monotonic()
    with lock_util.BackendLock(shared=shared, api_url=api_url):
        return time.monotonic() - t0


def test_shared_holders_overlap():
    url = _api_url("sh-overlap")
    p = _spawn_holder(url, shared=True, hold_s=3.0)
    try:
        assert _timed_acquire(url, shared=True) < 1.0
    finally:
        p.wait()


def test_exclusive_waits_for_shared_to_drain():
    url = _api_url("ex-waits")
    p = _spawn_holder(url, shared=True, hold_s=3.0)
    try:
        assert _timed_acquire(url, shared=False) >= 1.5
    finally:
        p.wait()


def test_shared_granted_while_exclusive_waits():
    """A stream of uploads keeps flowing while a test run queues — the
    test run must wait for ALL of it to drain. Intended semantics."""
    url = _api_url("sh-while-ex-waits")
    p_sh = _spawn_holder(url, shared=True, hold_s=5.0)
    p_ex = subprocess.Popen(
        [sys.executable, "-u", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import lock_util\n"
         "with lock_util.BackendLock(shared=False, api_url=sys.argv[2]): pass\n",
         TESTS_DIR, url],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        time.sleep(1.0)  # let the exclusive acquirer start waiting
        assert _timed_acquire(url, shared=True) < 1.0
    finally:
        p_sh.wait()
        assert p_ex.wait(timeout=30) == 0  # EX got in once SH drained


def test_kill_dash_nine_releases_lock():
    url = _api_url("kill-releases")
    p = _spawn_holder(url, shared=False, hold_s=60.0)
    p.kill()
    p.wait()
    assert _timed_acquire(url, shared=False) < 1.0


def test_holders_diagnostics():
    url = _api_url("holders")
    p = _spawn_holder(url, shared=False, hold_s=10.0)
    try:
        hs = lock_util.holders(lock_util.lock_path(url))
        assert any(str(p.pid) in h and "exclusive" in h for h in hs), hs
    finally:
        p.kill()
        p.wait()


# ---------------------------------------------------------------------------
# 5. TS helper holds the same kernel lock
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.exists(TSX),
                    reason=f"tsx not installed at {TSX} (run bun/npm install in frontend/)")
def test_ts_helper_interop():
    url = _api_url("ts-interop")
    code = (
        f"import {{ acquireTestLock, releaseTestLock, lockPath }} from '{TS_HELPER}';\n"
        "(async () => {\n"  # tsx -e emits CJS: no top-level await
        "  await acquireTestLock(false);\n"
        "  console.log('NODE_ACQUIRED ' + lockPath());\n"
        "  await new Promise(r => setTimeout(r, 3000));\n"
        "  releaseTestLock();\n"
        "})();\n"
    )
    env = dict(os.environ, API_URL=url)
    p = subprocess.Popen([TSX, "-e", code], cwd=FRONTEND_DIR, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True)
    try:
        deadline = time.monotonic() + 30
        for line in p.stdout:
            if line.startswith("NODE_ACQUIRED"):
                # Same derivation on both sides → same lock file.
                assert line.split()[1] == lock_util.lock_path(url)
                break
            assert time.monotonic() < deadline, "node helper never acquired"
        else:
            pytest.fail("node helper exited without acquiring")
        # Node holds exclusive → Python must see busy in both modes...
        import fcntl
        fd = os.open(lock_util.lock_path(url), os.O_CREAT | os.O_RDWR, 0o666)
        try:
            for op in (fcntl.LOCK_SH, fcntl.LOCK_EX):
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, op | fcntl.LOCK_NB)
            p.wait(timeout=30)
            # ...and acquire freely once the node side released.
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
    finally:
        p.kill()
        p.wait()
