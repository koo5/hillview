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


def _try_claim_stale_lock(stale_pid: int) -> bool:
    """Atomically claim a stale lock by renaming it first.

    Prevents the race where two processes both see a stale lock,
    both unlink it, and both create a new one.
    """
    temp_path = f"{LOCK_FILE}.claiming.{os.getpid()}"
    try:
        # rename is atomic on Linux — only one process can succeed.
        os.rename(LOCK_FILE, temp_path)
    except OSError:
        # Another process already renamed it — we lost the race.
        return False
    # We won the rename. Verify the file still contains the stale PID.
    try:
        with open(temp_path) as f:
            pid = int(f.read().strip())
        if pid != stale_pid:
            # Someone else acquired and we accidentally grabbed their lock — put it back.
            try:
                os.rename(temp_path, LOCK_FILE)
            except OSError:
                pass
            return False
    except (FileNotFoundError, ValueError):
        return False
    # Clean up the renamed stale file.
    try:
        os.unlink(temp_path)
    except FileNotFoundError:
        pass
    print(f"\nRemoved stale lock (dead PID {stale_pid})")
    return True


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
                    _try_claim_stale_lock(pid)
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
