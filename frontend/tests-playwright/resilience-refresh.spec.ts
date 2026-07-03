/**
 * Resilience: transient vs terminal token-refresh failures.
 *
 * - A 5xx (or timeout/network) refresh is TRANSIENT: keep the session, don't log out.
 * - A 401/403 refresh is TERMINAL: the token is genuinely rejected → log out.
 *
 * Both are triggered the same way: a 401 on the next authed call (or a force-logout)
 * makes the client force-refresh; the fault on /api/auth/refresh decides the flavor.
 */
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { armFault, clearFaults, forceLogoutUser } from './helpers/debugFaults';

test.describe('Resilience: refresh failures', () => {
    test.afterEach(async () => {
        await clearFaults();
        await forceLogoutUser('test', true); // clear the flag for other specs
    });

    test('transient (5xx) refresh keeps the session — no logout', async ({ page, testUsers }) => {
        await loginAsTestUser(page, testUsers.passwords.test);

        // 401 on the next authed call forces a refresh; the refresh itself 503s
        // (transient). The client must keep the session, not bounce to /login.
        await armFault('/api/auth/me', { status: 401, count: 1 });
        await armFault('/api/auth/refresh', { status: 503 });

        await page.goto('/');
        // Staying on the map (not bounced to /login) means the map renders.
        await page.locator('.leaflet-container').waitFor({ state: 'visible', timeout: 11*10000 }).catch(() => {});

        expect(page.url()).not.toContain('/login');

        // Heal + reconnect → the session keeps working.
        await clearFaults();
        await page.evaluate(() => window.dispatchEvent(new Event('online')));
        await page.waitForTimeout(2000);
        expect(page.url()).not.toContain('/login');
    });

    test('terminal (401) refresh logs out → /login', async ({ page, testUsers }) => {
        await loginAsTestUser(page, testUsers.passwords.test);

        // Server rejects this user's access + refresh tokens → terminal.
        await forceLogoutUser('test');

        // An authed call on load (fetchUserData → /auth/me) 401s → force-refresh →
        // /auth/refresh 401 → logout → /login.
        await page.goto('/');
        await page.waitForURL('**/login', { timeout: 20000 });
        expect(page.url()).toContain('/login');
    });
});
