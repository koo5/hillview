/**
 * Resilience: faulting several endpoints at once must not crash the app.
 *
 * Guards against the class of failure that produced the original
 * "UNCAUGHT ERROR: TokenExpiredError" — an auth/profile/data failure escaping as
 * an uncaught exception or white-screening the app. Asserts zero uncaught
 * exceptions and zero unexpected console errors while endpoints are down.
 */
import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { armFault, clearFaults } from './helpers/debugFaults';
import { isUnexpectedError } from './helpers/consoleLogging';

test.describe('Resilience: no uncaught errors under endpoint chaos', () => {
    // Keep tile requests routable across navigations; this test exercises API
    // recovery and does not depend on the service worker's tile fallback.
    test.use({ serviceWorkers: 'block' });

    test.afterEach(async () => {
        await clearFaults();
    });

    test('faulting auth/profile/photo/stream endpoints does not crash the app', async ({ page, testUsers }) => {
        // External tile availability must not decide whether API chaos crashed
        // the app. Fulfil tiles locally rather than ignoring CORS errors, which
        // could hide a real failure on one of the endpoints under test.
        await page.route('https://tiles4.ueueeu.eu/tile/**', route => route.fulfill({
            contentType: 'image/png',
            headers: { 'Access-Control-Allow-Origin': '*' },
            body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
        }));

        const uncaught: string[] = [];
        const consoleErrors: string[] = [];
        // Filter pageerrors through the same benign-error allowlist as console
        // errors. WebKit surfaces a navigation-aborted module-worker load as an
        // uncaught "Importing a module script failed" rejection (chromium routes
        // it only through worker.onerror); that's benign transient noise, not the
        // crash class this test guards against.
        page.on('pageerror', (e) => { if (isUnexpectedError(String(e))) uncaught.push(String(e)); });
        page.on('console', (msg) => {
            if (msg.type() === 'error' && isUnexpectedError(msg.text())) consoleErrors.push(msg.text());
        });

        await loginAsTestUser(page, testUsers.passwords.test);

        // Chaos: nuke several endpoints, then drive the app through them.
        await armFault('/api/auth/me', { status: 500 });
        await armFault('/api/auth/refresh', { status: 503 });
        await armFault('/api/photos/*', { status: 500 });
        await armFault('/api/hillview*', { status: 500 });

        await page.goto('/');
        await page.goto('/account-deletion').catch(() => {});
        await page.waitForTimeout(2000);

        // Heal and return to the map — the app should be fully functional again.
        await clearFaults();
        await page.goto('/');
        // App should recover once faults are cleared: the map re-renders.
        await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: T(15000) });

        expect(uncaught, `uncaught exceptions: ${uncaught.join(' | ')}`).toHaveLength(0);
        expect(consoleErrors, `unexpected console errors: ${consoleErrors.join(' | ')}`).toHaveLength(0);
    });
});
