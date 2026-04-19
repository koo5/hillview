"""Backend integration-test lock.

Shared between pytest (via conftest.py) and shell scripts that need to
serialize destructive operations against the shared dev backend.
"""
import argparse
import os
import time

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
        os.rename(LOCK_FILE, temp_path)
    except OSError:
        return False
    try:
        with open(temp_path) as f:
            pid = int(f.read().strip())
        if pid != stale_pid:
            try:
                os.rename(temp_path, LOCK_FILE)
            except OSError:
                pass
            return False
    except (FileNotFoundError, ValueError):
        return False
    try:
        os.unlink(temp_path)
    except FileNotFoundError:
        pass
    print(f"\nRemoved stale lock (dead PID {stale_pid})")
    return True


def acquire_lock(owner_pid: int | None = None) -> None:
    """Acquire the backend test lock, writing `owner_pid` (default: os.getpid()) into the file."""
    pid_to_write = owner_pid if owner_pid is not None else os.getpid()
    start = time.monotonic()
    while True:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(pid_to_write).encode())
            os.close(fd)
            print(f"\nTest lock acquired (PID {pid_to_write})")
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


def release_lock(owner_pid: int | None = None) -> None:
    """Release the backend test lock iff held by `owner_pid` (default: os.getpid())."""
    expected_pid = owner_pid if owner_pid is not None else os.getpid()
    try:
        with open(LOCK_FILE) as f:
            pid = int(f.read().strip())
        if pid == expected_pid:
            os.unlink(LOCK_FILE)
            print(f"\nTest lock released (PID {expected_pid})")
    except (FileNotFoundError, ValueError):
        pass


def _main() -> None:
    parser = argparse.ArgumentParser(description='Acquire/release the backend integration test lock.')
    parser.add_argument('action', choices=['acquire', 'release'])
    parser.add_argument('--pid', type=int, default=None,
                        help='PID to write to the lock file (default: own PID)')
    args = parser.parse_args()
    if args.action == 'acquire':
        acquire_lock(args.pid)
    else:
        release_lock(args.pid)


if __name__ == '__main__':
    _main()
