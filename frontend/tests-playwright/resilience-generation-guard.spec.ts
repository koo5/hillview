/**
 * Resilience: a stale request from a PREVIOUS session can't tear down a fresh login.
 *
 * This is the original production bug: open the app, a refresh fails → logout →
 * /login → you re-login, but a still-in-flight authed request from the old session
 * then resolves and calls logout() again, nuking the new session. The auth
 * "generation" guard ignores a logout requested by a request that began in an older
 * generation.
 *
 * NOTE: this is the trickiest spec to make non-flaky — it relies on a slow refresh
 * staying in flight across a re-login. Everything below stays in the same JS context
 * (SPA navigation only; NO page.goto / reload), because a full navigation would
 * cancel the in-flight request. Timing (the 12s refresh delay vs. logout+re-login)
 * may need tuning per machine.
 */
import { test, expect } from './fixtures';
import { loginAsTestUser, logoutUser } from './helpers/testUsers';
import { armFault, clearFaults, forceLogoutUser } from './helpers/debugFaults';

const REFRESH_DELAY = 12; // seconds the stale refresh hangs before its 401 lands

test.describe('Resilience: generation guard', () => {
    test.afterEach(async () => {
        await clearFaults();
        await forceLogoutUser('test', true);
    });

    test('a stale logout from the previous session is ignored after re-login', async ({ page, testUsers }) => {
        const password = testUsers.passwords.test;
        await loginAsTestUser(page, password);

        // Make the next authed photo request 401, and the resulting refresh 401
        // *slowly* — so the logout it triggers lands AFTER we've re-logged-in.
        await armFault('/api/photos/*', { status: 401, count: 1 });
        await armFault('/api/auth/refresh', { status: 401, delaySeconds: REFRESH_DELAY, count: 1 });

        // Kick off the doomed flow via SPA nav (My Photos → fetch → 401 → force-refresh,
        // which now hangs). Wait so the refresh request reaches the server (and is held).
        await page.getByLabel('Toggle menu').click();
        await page.getByTestId('my-photos-link').click();
        await page.waitForTimeout(3000);

        // Clear faults so the rest of the flow (re-login) succeeds. The already-held
        // refresh keeps its 401 (matched server-side before the clear).
        await clearFaults();

        // First (legitimate) logout → /login, then re-login. Both are SPA-only so the
        // stale refresh promise survives. This re-login bumps the auth generation.
        await logoutUser(page);
        await page.getByTestId('login-username-input').fill('test');
        await page.getByTestId('login-password-input').fill(password);
        await page.getByTestId('login-submit-button').click();
        await page.waitForURL('/', { timeout: 20000 });

        // Let the stale (gen-1) refresh resolve; its 401 → logout(gen 1) must be ignored.
        await page.waitForTimeout(REFRESH_DELAY * 1000);

        // The fresh session survives — we're not bounced back to /login.
        expect(page.url()).not.toContain('/login');
    });
});
