/**
 * E2E: a TRANSIENT token-refresh failure must NOT log the user out.
 *
 * Validates "don't nuke the session over a connectivity blip": when a refresh times
 * out (vs. the server rejecting the token), the native side keeps the tokens (clears
 * only on 401) and the WebView stays authenticated — then recovers once refreshes
 * succeed again.
 *
 * Made deterministic by two internal debug hooks (localhost-guarded):
 *   - setAccessTtl(): short access token, so the client crosses its proactive-refresh
 *     window quickly. Must exceed the client's ~2-min refresh buffer to leave a valid
 *     post-login window.
 *   - setDebugDelay('auth_refresh', n): slow refresh, so it exceeds the native OkHttp
 *     read timeout (~10s) → times out → transient failure (NOT a 401).
 *
 * Requires the dev app (cz.hillviedev) + backend at localhost:8055 with the api
 * container rebuilt to include the hooks.
 */

import { browser } from '@wdio/globals';
import { byTestId, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, setAccessTtl, setDebugDelay } from '../helpers/backend';
import { invokePlugin } from '../helpers/bridge';
import { isLoggedInUI } from '../helpers/authUi';

const ACCESS_TTL_SECONDS = 130; // > the client's 2-min proactive-refresh buffer
const REFRESH_DELAY_SECONDS = 25; // > native OkHttp read timeout (~10s)

describe('Transient refresh failure keeps the session', function () {
    this.timeout(240000);

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
        // Short-lived access token (override read at login) + slow refresh.
        await setAccessTtl('test', ACCESS_TTL_SECONDS);
        await setDebugDelay('auth_refresh', REFRESH_DELAY_SECONDS);

        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
        await loginAsTestUser();
        expect(await isLoggedInUI()).toBe(true);
    });

    after(async () => {
        try {
            await setDebugDelay('auth_refresh', 0);
            await setAccessTtl('test', 0, true);
        } catch {
            // best effort
        }
    });

    it('stays logged in when a refresh times out, and recovers when refresh succeeds', async () => {
        // Let the short access token cross the client's refresh buffer, then force a
        // refresh — it exceeds the native read timeout and fails TRANSIENTLY.
        await browser.pause(15000);
        await invokePlugin('plugin:hillview|refresh_auth_token');
        await browser.pause(2000);

        // Transient failure must NOT log out: tokens are kept (cleared only on 401).
        expect(await isLoggedInUI()).toBe(true);

        // Clear the delay → a subsequent refresh succeeds → session is healthy.
        await setDebugDelay('auth_refresh', 0);
        await invokePlugin('plugin:hillview|refresh_auth_token');
        await browser.pause(3000);

        expect(await isLoggedInUI()).toBe(true);
    });
});
