/**
 * Resilience: a failed profile load self-heals on reconnect (no manual retry).
 *
 * After a transient /api/auth/me failure leaves userStatus:'error', firing an
 * `online` event must auto-retry the profile fetch (retryUserData wired to
 * online/visibilitychange in auth.svelte).
 */
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { armFault, clearFaults } from './helpers/debugFaults';

test.describe('Resilience: auto-retry on reconnect', () => {
    test.afterEach(async () => {
        await clearFaults();
    });

    test('profile auto-loads on the online event without a manual retry', async ({ page, testUsers }) => {
        await loginAsTestUser(page, testUsers.passwords.test);

        await armFault('/api/auth/me', { status: 500 });
        await page.goto('/account-deletion');
        await expect(page.getByTestId('loadable-error')).toBeVisible({ timeout: 15000 });

        // Heal the backend and fire the reconnect signal — no click on Retry.
        await clearFaults();
        await page.evaluate(() => window.dispatchEvent(new Event('online')));

        await expect(page.getByText(/logged in as/i)).toBeVisible({ timeout: 15000 });
        await expect(page.getByTestId('loadable-error')).toBeHidden();
    });
});
