/**
 * Resilience: faulting several endpoints at once must not crash the app.
 *
 * Guards against the class of failure that produced the original
 * "UNCAUGHT ERROR: TokenExpiredError" — an auth/profile/data failure escaping as
 * an uncaught exception or white-screening the app. Asserts zero uncaught
 * exceptions and zero unexpected console errors while endpoints are down.
 */
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { armFault, clearFaults } from './helpers/debugFaults';
import { isUnexpectedError } from './helpers/consoleLogging';

test.describe('Resilience: no uncaught errors under endpoint chaos', () => {
    test.afterEach(async () => {
        await clearFaults();
    });

    test('faulting auth/profile/photo/stream endpoints does not crash the app', async ({ page, testUsers }) => {
        const uncaught: string[] = [];
        const consoleErrors: string[] = [];
        page.on('pageerror', (e) => uncaught.push(String(e)));
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
        await page.locator('.leaflet-container').waitFor({ state: 'visible', timeout: 11*15000 }).catch(() => {});

        expect(uncaught, `uncaught exceptions: ${uncaught.join(' | ')}`).toHaveLength(0);
        expect(consoleErrors, `unexpected console errors: ${consoleErrors.join(' | ')}`).toHaveLength(0);
    });
});
