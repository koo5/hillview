/**
 * End-to-end test for the "Login Required" Android system notification
 * that fires when the user's session is invalidated server-side.
 *
 * Full flow exercised:
 *   1. Backend marks the user as force-logged-out
 *      (`POST /api/internal/debug/force-logout-user`, a process-memory
 *      flag added in auth.py + internal_debug_routes.py).
 *   2. Android app runs the upload worker (via `tryUploads`).
 *   3. Worker calls `POST /api/photos/authorize-upload` with its
 *      locally-still-valid access token → backend returns 401 because
 *      of the force-logout flag.
 *   4. PhotoUploadLogic.requestUploadAuthorization detects the 401 and
 *      invokes AuthenticationManager.forceRefreshToken().
 *   5. That POSTs to /api/auth/refresh-token with the refresh token;
 *      the backend also honors the flag there and returns 401.
 *   6. AuthenticationManager.performTokenRefresh sees 401, clears stored
 *      tokens, and calls NotificationHelper.showAuthExpiredNotification()
 *      — system notification titled "Login Required", channel
 *      "auth_notifications", id 1001.
 *
 * Verified via `dumpsys notification` (requires the
 * `uiautomator2:adb_shell` opt-in in wdio.conf.ts).
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, forceLogoutUser } from '../helpers/backend';
import { captureOnePhoto, enableAutoUpload } from '../helpers/uploadFlow';
import { invokePlugin } from '../helpers/bridge';

const APP_PACKAGE = 'cz.hillviedev';
const NOTIFICATION_TITLE = 'Login Required';

// -------------------- dumpsys helpers --------------------

async function getNotificationsDump(): Promise<string> {
    const out = (await (driver as any).execute('mobile: shell', {
        command: 'dumpsys',
        args: ['notification', '--noredact'],
        includeStderr: true,
    })) as string | { stdout: string };
    return typeof out === 'string' ? out : out?.stdout ?? '';
}

async function cancelNotification(id: number): Promise<void> {
    try {
        await (driver as any).execute('mobile: shell', {
            command: 'cmd',
            args: ['notification', 'cancel', APP_PACKAGE, String(id)],
            includeStderr: true,
        });
    } catch {
        // best effort
    }
    await browser.pause(500);
}

async function waitForNotification(title: string, timeoutMs: number): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    let lastDump = '';
    while (Date.now() < deadline) {
        lastDump = await getNotificationsDump();
        if (lastDump.includes(title)) return lastDump;
        await browser.pause(500);
    }
    return lastDump;
}

function extractNotificationBlock(dump: string, title: string): string[] {
    const lines = dump.split('\n');
    const idx = lines.findIndex((l) => l.includes(title));
    if (idx < 0) return [];
    let start = idx;
    for (let i = idx; i >= Math.max(0, idx - 40); i--) {
        if (/NotificationRecord|sbn=|pkg=cz\.hillviedev/.test(lines[i])) {
            start = i;
            break;
        }
    }
    const end = Math.min(lines.length, idx + 12);
    return lines.slice(start, end).map((l) => l.replace(/\s+$/, ''));
}

// -------------------- test --------------------

describe('Re-login required system notification', function () {
    // Default mocha timeout is 60s; this test's flow has several multi-second
    // Waits so bump it for the whole describe.
    this.timeout(240000);

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);

        await ensureWebViewContext();
        const source = await browser.getPageSource();
        if (source.includes('error sending request')) {
            await browser.refresh();
            await browser.pause(5000);
        }

        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });

        await loginAsTestUser();

        // Need mockCamera so the capture actually produces a unique frame.
        await ensureWebViewContext();
        await browser.execute(() => localStorage.setItem('mockCamera', 'true'));

        // DON'T enable auto-upload here — we want the photo captured in
        // the test body to stay pending until we've armed the force-logout
        // flag. Otherwise the already-scheduled worker can drain the queue
        // with a still-valid token before we get a chance to invalidate.
    });

    after(async () => {
        // Ensure subsequent specs don't inherit the force-logout flag.
        try {
            await forceLogoutUser('test', true);
        } catch {
            // best effort
        }
    });

    it('fires "Login Required" when the server rejects the access token and refresh', async () => {
        await cancelNotification(1001);

        // Queue a pending photo BEFORE enabling auto-upload so the worker
        // doesn't race us and drain it with a still-valid token.
        await captureOnePhoto(false);

        // Invalidate sessions server-side. Any access-token or refresh
        // call for this user now returns 401.
        await forceLogoutUser('test');

        // Enable auto-upload (schedules the periodic worker) AND fire
        // tryUploads for a deterministic expedited run. With the pending
        // photo in the queue and auto-upload on, the worker hits
        // POST /api/photos/authorize-upload → 401 → forceRefreshToken →
        // /api/auth/refresh → 401 → showAuthExpiredNotification().
        await enableAutoUpload();
        await invokePlugin('plugin:hillview|tryUploads');

        const dump = await waitForNotification(NOTIFICATION_TITLE, 30000);
        expect(dump).toContain(NOTIFICATION_TITLE);

        const block = extractNotificationBlock(dump, NOTIFICATION_TITLE);
        console.log('[relogin-notif] "Login Required" notification snippet:');
        for (const line of block) console.log(`[relogin-notif]   ${line}`);
        console.log('[relogin-notif] holding 20s for visual verification...');
        await browser.pause(20000);
    });
});
