/**
 * E2E: a 5xx token-refresh failure is TRANSIENT — the session is kept (native).
 *
 * Complements native-transient-refresh-keeps-session.test.ts (which uses a slow
 * refresh / timeout): here the refresh returns 503. AuthenticationManager clears
 * tokens only on 401, so a 503 must NOT log the user out, and the session recovers
 * once the fault clears.
 *
 * Requires the dev app (cz.hillviedev) + backend at localhost:8055 with the
 * fault-injection middleware and DEBUG_ENDPOINTS enabled.
 */
import { browser } from '@wdio/globals';
import { byTestId, TESTID } from '../helpers/selectors';
import { recreateTestUsers, loginAsTestUser, setAccessTtl, armFault, clearFaults } from '../helpers/backend';
import { invokePlugin } from '../helpers/bridge';
import { isLoggedInUI } from '../helpers/authUi';

const ACCESS_TTL_SECONDS = 130; // > the client's 2-min proactive-refresh buffer

describe('A 5xx refresh failure keeps the session (native)', function () {
    this.timeout(180000);

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
        await setAccessTtl('test', ACCESS_TTL_SECONDS); // short token → client refreshes soon
        await armFault('/api/auth/refresh', { status: 503 });

        const menu = await byTestId(TESTID.hamburgerMenu);
        await menu.waitForDisplayed({ timeout: 30000 });
        await loginAsTestUser();
        expect(await isLoggedInUI()).toBe(true);
    });

    after(async () => {
        try {
            await clearFaults();
            await setAccessTtl('test', 0, true);
        } catch {
            // best effort
        }
    });

    it('stays logged in when the refresh returns 503, recovers when cleared', async () => {
        // Let the short token cross the refresh buffer, then force a refresh → 503.
        await browser.pause(15000);
        await invokePlugin('plugin:hillview|refresh_auth_token');
        await browser.pause(2000);

        // 503 ≠ 401 → native keeps the tokens → still logged in.
        expect(await isLoggedInUI()).toBe(true);

        // Clear the fault → the next refresh succeeds → session healthy.
        await clearFaults();
        await invokePlugin('plugin:hillview|refresh_auth_token');
        await browser.pause(3000);
        expect(await isLoggedInUI()).toBe(true);
    });
});
