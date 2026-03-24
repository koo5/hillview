/**
 * Acquires the shared test lock, then spawns a child process.
 * Ensures the lock is held before Appium/wdio starts,
 * preventing port conflicts between parallel test runs.
 */
import { acquireTestLock, releaseTestLock } from '../../tests-playwright/helpers/testLock';
import { spawn } from 'child_process';

async function main() {
    const args = process.argv.slice(2);
    if (args.length === 0) {
        console.error('Usage: lockAndRun <command> [args...]');
        process.exit(1);
    }

    await acquireTestLock();

    const child = spawn(args[0], args.slice(1), {
        stdio: 'inherit',
        env: process.env,
    });

    child.on('exit', (code) => {
        releaseTestLock();
        process.exit(code ?? 1);
    });

    child.on('error', (err) => {
        console.error('Failed to start child process:', err.message);
        releaseTestLock();
        process.exit(1);
    });

    // Forward signals so Ctrl-C kills the child and releases the lock
    for (const sig of ['SIGINT', 'SIGTERM'] as const) {
        process.on(sig, () => {
            child.kill(sig);
        });
    }
}

main().catch((err) => {
    console.error('lockAndRun error:', err.message);
    releaseTestLock();
    process.exit(1);
});
