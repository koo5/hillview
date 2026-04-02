/**
 * Shared test lock used by Playwright, pytest, and Appium test suites.
 * Prevents port conflicts and backend state races between parallel test runs.
 *
 * This is a standalone copy — the Playwright suite has its own identical copy
 * at tests-playwright/helpers/testLock.ts. Both use the same lock file.
 */
import fs from 'fs';

const LOCK_FILE = '/tmp/hillview-test-backend.lock';
const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
const POLL_MS = 1000;

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export async function acquireTestLock(): Promise<void> {
  const start = Date.now();
  while (true) {
    try {
      const fd = fs.openSync(LOCK_FILE, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY);
      fs.writeSync(fd, String(process.pid));
      fs.closeSync(fd);
      console.log(`Test lock acquired (PID ${process.pid})`);
      return;
    } catch (err: any) {
      if (err.code !== 'EEXIST') throw err;

      // Lock exists - check staleness
      try {
        const content = fs.readFileSync(LOCK_FILE, 'utf-8').trim();
        const pid = parseInt(content, 10);
        if (!isNaN(pid) && !isProcessAlive(pid)) {
          console.log(`Removing stale lock (dead PID ${pid})`);
          fs.unlinkSync(LOCK_FILE);
          continue;
        }
        if (Date.now() - start > TIMEOUT_MS) {
          throw new Error(`Timed out waiting for test lock (held by PID ${pid})`);
        }
        console.log(`Waiting for test lock (held by PID ${pid})...`);
      } catch (readErr: any) {
        if (readErr.code === 'ENOENT') continue; // Lock was just released
        throw readErr;
      }
    }
    await new Promise(r => setTimeout(r, POLL_MS));
  }
}

export function releaseTestLock(): void {
  try {
    const content = fs.readFileSync(LOCK_FILE, 'utf-8').trim();
    const pid = parseInt(content, 10);
    if (pid === process.pid) {
      fs.unlinkSync(LOCK_FILE);
      console.log(`Test lock released (PID ${process.pid})`);
    }
  } catch {
    // Lock already gone - fine
  }
}
