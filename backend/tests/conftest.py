import os
import time
import pytest

LOCK_FILE = '/tmp/hillview-test-backend.lock'
TIMEOUT_S = 5 * 60
POLL_S = 1


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_lock():
    start = time.monotonic()
    while True:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            print(f"\nTest lock acquired (PID {os.getpid()})")
            return
        except FileExistsError:
            try:
                with open(LOCK_FILE) as f:
                    pid = int(f.read().strip())
                if not _is_process_alive(pid):
                    print(f"\nRemoving stale lock (dead PID {pid})")
                    os.unlink(LOCK_FILE)
                    continue
                if time.monotonic() - start > TIMEOUT_S:
                    raise TimeoutError(f"Timed out waiting for test lock (held by PID {pid})")
                print(f"\nWaiting for test lock (held by PID {pid})...")
            except FileNotFoundError:
                continue
        time.sleep(POLL_S)


def _release_lock():
    try:
        with open(LOCK_FILE) as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            os.unlink(LOCK_FILE)
            print(f"\nTest lock released (PID {os.getpid()})")
    except (FileNotFoundError, ValueError):
        pass


@pytest.fixture(scope="session", autouse=True)
def backend_test_lock():
    _acquire_lock()
    yield
    _release_lock()
