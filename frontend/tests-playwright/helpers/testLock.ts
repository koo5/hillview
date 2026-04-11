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

/**
 * Try to atomically claim a stale lock by renaming it first.
 * This prevents the race where two processes both see a stale lock,
 * both unlink it, and both create a new one.
 */
function tryClaimStaleLock(stalePid: number): boolean {
  const tempPath = `${LOCK_FILE}.claiming.${process.pid}`;
  try {
    // Rename is atomic on Linux — only one process can succeed.
    fs.renameSync(LOCK_FILE, tempPath);
  } catch {
    // Another process already renamed it — we lost the race.
    return false;
  }
  // We won the rename. Verify the file still contains the stale PID
  // (not a fresh lock from someone who acquired between our read and rename).
  try {
    const content = fs.readFileSync(tempPath, 'utf-8').trim();
    const pid = parseInt(content, 10);
    if (pid !== stalePid) {
      // Someone else acquired and we accidentally grabbed their lock — put it back.
      try { fs.renameSync(tempPath, LOCK_FILE); } catch { /* best effort */ }
      return false;
    }
  } catch {
    return false;
  }
  // Clean up the renamed stale file.
  try { fs.unlinkSync(tempPath); } catch { /* already gone */ }
  console.log(`Removed stale lock (dead PID ${stalePid})`);
  return true;
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
          if (tryClaimStaleLock(pid)) continue;
          // Lost the race — another process claimed it, loop and retry.
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
