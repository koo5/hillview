/**
 * Backend integration lock — per-API-server, shared/exclusive.
 *
 * TypeScript port of backend/tests/lock_util.py (the authoritative writeup
 * of the protocol lives there). Built on flock(2):
 *
 * - Lock file is per API server, derived from $API_URL (same derivation as
 *   the Python side — keep them in sync). Playwright/Appium runs that don't
 *   set API_URL lock the default local dev server.
 * - Shared holders (uploads) overlap each other; an exclusive holder (test
 *   runs — this module's default) excludes everyone, and waits for the whole
 *   in-flight shared stream to drain before it gets in.
 * - The kernel drops the flock when the holding process dies, so there are
 *   no stale locks and no PID-liveness machinery. The lock file is never
 *   unlinked (that would split the lock onto a fresh inode).
 *
 * Node has no flock binding, so acquisition spawns flock(1) on an fd we
 * opened and pass down: the child locks the *open file description* and
 * exits; the lock stays with our fd and dies with our process.
 */
import fs from 'fs';
import { spawnSync } from 'child_process';

const POLL_MS = 1000;
const DEFAULT_API_URL = 'http://localhost:8055/api';

export function lockPath(apiUrl?: string): string {
  let url = apiUrl || process.env.API_URL || DEFAULT_API_URL;
  if (!url.includes('://')) url = 'http://' + url;
  const u = new URL(url);
  // Match lock_util.lock_path(): lowercase host, brackets stripped, ':' → '_'
  // (IPv6), explicit port defaulted by scheme.
  const host = u.hostname.toLowerCase().replace(/[[\]]/g, '').replace(/:/g, '_');
  const port = u.port || (u.protocol === 'https:' ? '443' : '80');
  return `/tmp/hillview-test-backend.${host}_${port}.lock`;
}

/** Best-effort live holder list from /proc/locks (matched by inode only). */
function holders(path: string): string[] {
  try {
    const ino = fs.statSync(path).ino;
    const out: string[] = [];
    for (const line of fs.readFileSync('/proc/locks', 'utf-8').split('\n')) {
      // e.g.: "42: FLOCK  ADVISORY  WRITE 12345 fd:01:9184716 0 EOF"
      const parts = line.split(/\s+/);
      const i = parts.indexOf('FLOCK');
      if (i >= 0 && parts[i + 4]?.endsWith(`:${ino}`)) {
        const mode = parts[i + 2] === 'WRITE' ? 'exclusive' : 'shared';
        out.push(`${parts[i + 3]} (${mode})`);
      }
    }
    return out;
  } catch {
    return [];
  }
}

let lockFd: number | null = null;

/**
 * Acquire the backend test lock (exclusive by default — test runs must not
 * overlap anything). Waits indefinitely; a holder's run may legitimately
 * outlast any fixed timeout. Interrupt the process to abort.
 */
export async function acquireTestLock(shared = false): Promise<void> {
  if (lockFd !== null) throw new Error('test lock already held by this process');
  const path = lockPath();
  const mode = shared ? 'shared' : 'exclusive';
  // 'a' = O_CREAT without truncating: never disturb the file others lock.
  const fd = fs.openSync(path, 'a');
  while (true) {
    // flock(1)'s <fd-number> form locks an inherited fd: the child flocks
    // our open file description and exits, leaving the lock on our fd.
    const res = spawnSync('flock', [`--${mode}`, '--nonblock', '3'], {
      stdio: ['ignore', 'inherit', 'inherit', fd],
    });
    if (res.error) {
      fs.closeSync(fd);
      throw res.error;
    }
    if (res.status === 0) break;
    const held = holders(path);
    const by = held.length ? ` (held by ${held.join(', ')})` : '';
    console.log(`Waiting for ${mode} lock ${path}${by}...`);
    await new Promise(r => setTimeout(r, POLL_MS));
  }
  lockFd = fd;
  console.log(`Acquired ${mode} lock ${path} (PID ${process.pid})`);
}

export function releaseTestLock(): void {
  if (lockFd !== null) {
    fs.closeSync(lockFd); // closing the fd drops the flock
    lockFd = null;
    console.log(`Released test lock (PID ${process.pid})`);
  }
}
