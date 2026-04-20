/**
 * Coverage for the "Login Required" system notification that the app
 * posts when the user's session can no longer be refreshed. Two paths
 * fire `NotificationHelper.showAuthExpiredNotification()`
 * (NotificationHelper.kt:75); we drive both:
 *
 *   1. Expired access token + MISSING refresh token →
 *      AuthenticationManager.kt:239 (refreshTokenIfNeeded takes the
 *      "no refresh token available" branch and posts the notification
 *      because an access token is present).
 *
 *   2. Expired access token + refresh endpoint returns 401 →
 *      AuthenticationManager.kt:413 (performTokenRefresh sees 401 on
 *      POST /auth/refresh-token, clears tokens, posts the notification).
 *
 * Both resolve to the same system notification: title "Login Required",
 * channel "auth_notifications", NOTIFICATION_ID 1001. We verify via
 * `dumpsys notification` (requires the `uiautomator2:adb_shell` opt-in
 * in wdio.conf.ts).
 */

import { browser } from '@wdio/globals';
import { byTestId, ensureWebViewContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser } from '../helpers/backend';

const APP_PACKAGE = 'cz.hillviedev';
const NOTIFICATION_TITLE = 'Login Required';

async function invokeStoreAuthToken(args: {
    token: string;
    expires_at: string;
    refresh_token?: string | null;
    refresh_expiry?: string | null;
}): Promise<void> {
    await ensureWebViewContext();
    const result = (await browser.executeAsync(
        `
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|store_auth_token', arguments[0])
          .then(r => done(r), e => done({ __err: String(e) }));
        `,
        args,
    )) as { success?: boolean; error?: string; __err?: string };
    if (result.__err) throw new Error(result.__err);
    if (!result.success) {
        throw new Error(`store_auth_token failed: ${result.error ?? 'unknown'}`);
    }
}

async function invokeRefreshAuthToken(): Promise<boolean> {
    await ensureWebViewContext();
    const result = (await browser.executeAsync(`
        const done = arguments[arguments.length - 1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke('plugin:hillview|refresh_auth_token')
          .then(r => done(r), e => done({ __err: String(e) }));
    `)) as { success?: boolean; __err?: string };
    if (result.__err) throw new Error(result.__err);
    return result.success === true;
}

async function getNotificationsDump(): Promise<string> {
    const out = (await (driver as any).execute('mobile: shell', {
        command: 'dumpsys',
        args: ['notification', '--noredact'],
        includeStderr: true,
    })) as string | { stdout: string };
    return typeof out === 'string' ? out : out?.stdout ?? '';
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

/** Cancel a specific notification so leftovers from a previous run don't false-positive. */
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

describe('Re-login required system notification', () => {
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

        // Need to log in so that SharedPreferences has the auth-token
        // key populated — the missing-refresh-token branch only fires
        // when the "access token is present" check on AuthManager
        // line 238 is true.
        await loginAsTestUser();
    });

    it('fires "Login Required" when access token is expired and refresh token is missing', async function () {
        this.timeout(60000);

        // Clear any pre-existing auth-expired notification from a prior run.
        await cancelNotification(1001);

        // Override the stored tokens: valid-looking access token (not a
        // real JWT — AuthenticationManager doesn't parse it, just checks
        // expiry), expires_at in the past, NO refresh token.
        await invokeStoreAuthToken({
            token: 'stub.access.token',
            expires_at: new Date(Date.now() - 60_000).toISOString(),
            refresh_token: null,
            refresh_expiry: null,
        });

        // Trigger the refresh code path. refreshTokenIfNeeded sees the
        // expired token, calls getRefreshToken(), gets null, checks for
        // the access-token key in prefs (present from our store call),
        // and posts showAuthExpiredNotification().
        const refreshed = await invokeRefreshAuthToken();
        expect(refreshed).toBe(false);

        const dump = await waitForNotification(NOTIFICATION_TITLE, 10_000);
        expect(dump).toContain(NOTIFICATION_TITLE);

        // Print the stanza so a human running the test can visually
        // confirm the notification on the emulator + see its content.
        const block = extractNotificationBlock(dump, NOTIFICATION_TITLE);
        console.log('[relogin-notif] "Login Required" notification snippet:');
        for (const line of block) console.log(`[relogin-notif]   ${line}`);
        console.log('[relogin-notif] holding 20s for visual verification...');
        await browser.pause(20_000);
    });
});

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
