"""Backend integration lock — per-API-server, shared/exclusive.

Serializes work against a dev backend between pytest (conftest.py), the
Playwright/Appium helpers (frontend/tests-*/helpers/testLock.ts) and
debug.sh commands. Built on flock(2):

- The lock file is per API server: /tmp/hillview-test-backend.<host>_<port>.lock,
  derived from the effective API URL (lock_path()). Work against different
  servers never contends. Note the derivation is literal — "localhost" and
  "127.0.0.1" are different lock files.
- Holders pick a mode. SHARED holders (additive operations: uploads) overlap
  freely with each other. An EXCLUSIVE holder (test runs, destructive
  commands like recreate/cleanup) excludes everyone. flock grants new shared
  locks even while an exclusive acquirer waits — intentionally: a test run
  must wait for the whole in-flight upload stream to drain, however long
  that takes.
- The kernel drops a flock when the holding process dies (any signal, OOM,
  crash) — there are no stale locks and no PID-liveness machinery. Holder
  PIDs shown while waiting are read live from /proc/locks, purely
  informational.
- The lock file is never unlinked: removing it while others hold/await the
  inode would split the lock (a new opener locks a fresh inode). Empty lock
  files accumulating in /tmp are the intended steady state.

Shell scripts can take the same lock via flock(1):

    flock --shared "$(python tests/lock_util.py path)" -c '...'
"""
import argparse
import fcntl
import os
import time
from urllib.parse import urlparse

DEFAULT_API_URL = "http://localhost:8055/api"
POLL_S = 1


def lock_path(api_url: str | None = None) -> str:
    """Lock file path for `api_url` (default: $API_URL, else DEFAULT_API_URL)."""
    url = api_url or os.environ.get("API_URL") or DEFAULT_API_URL
    if "://" not in url:
        url = "http://" + url
    u = urlparse(url)
    # ':' in bare IPv6 hosts is awkward in filenames; '_' keeps it readable.
    host = (u.hostname or "localhost").lower().replace(":", "_")
    port = u.port or (443 if u.scheme == "https" else 80)
    return f"/tmp/hillview-test-backend.{host}_{port}.lock"


def holders(path: str) -> list[str]:
    """Best-effort live holder list ("<pid> (shared|exclusive)") from /proc/locks."""
    try:
        st = os.stat(path)
    except OSError:
        return []
    want = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    out = []
    try:
        with open("/proc/locks") as f:
            for line in f:
                # e.g.: "42: FLOCK  ADVISORY  WRITE 12345 fd:01:9184716 0 EOF"
                parts = line.split()
                if "FLOCK" in parts:
                    i = parts.index("FLOCK")
                    if parts[i + 4] == want:
                        mode = "exclusive" if parts[i + 2] == "WRITE" else "shared"
                        out.append(f"{parts[i + 3]} ({mode})")
    except OSError:
        return []
    return out


class BackendLock:
    """One shared or exclusive slot on the per-server backend lock.

    Context manager; may also be acquire()d / release()d explicitly. Each
    instance owns its own fd, so independent locks within one process don't
    interfere. Waits indefinitely (a holder's run may legitimately outlast
    any fixed timeout); interrupt the process to abort.
    """

    def __init__(self, shared: bool = False, api_url: str | None = None):
        self.shared = shared
        self.path = lock_path(api_url)
        self._fd: int | None = None

    @property
    def _mode(self) -> str:
        return "shared" if self.shared else "exclusive"

    def acquire(self) -> None:
        assert self._fd is None, "lock already held by this BackendLock"
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o666)
        op = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
        while True:
            try:
                fcntl.flock(fd, op | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                held = holders(self.path)
                by = f" (held by {', '.join(held)})" if held else ""
                print(f"\nWaiting for {self._mode} lock {self.path}{by}...")
                time.sleep(POLL_S)
        self._fd = fd
        print(f"\nAcquired {self._mode} lock {self.path} (PID {os.getpid()})")

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)  # closing the fd drops the flock
            self._fd = None
            print(f"\nReleased {self._mode} lock {self.path} (PID {os.getpid()})")

    def __enter__(self) -> "BackendLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


# Module-level convenience pair for the common one-lock-per-process case
# (pytest's session fixture in conftest.py).
_process_lock: BackendLock | None = None


def acquire_lock(shared: bool = False, api_url: str | None = None) -> None:
    global _process_lock
    assert _process_lock is None, "process lock already held"
    _process_lock = BackendLock(shared=shared, api_url=api_url)
    _process_lock.acquire()


def release_lock() -> None:
    global _process_lock
    if _process_lock is not None:
        _process_lock.release()
        _process_lock = None


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Backend test lock utilities. A lock can only be HELD by "
                    "a live process (flock dies with its holder), so there is "
                    "no acquire/release CLI — use flock(1) with `path`.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("path", help="print the lock file path for an API server")
    p.add_argument("--api-url", default=None,
                   help="API base URL (default: $API_URL, else %s)" % DEFAULT_API_URL)
    args = parser.parse_args()
    if args.cmd == "path":
        print(lock_path(args.api_url))


if __name__ == '__main__':
    _main()
