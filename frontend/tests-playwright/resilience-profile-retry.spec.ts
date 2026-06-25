/**
 * Resilience: profile load failure → the Loadable error/retry state → recovery.
 *
 * The user profile (/api/auth/me) is a separate request from authentication. When
 * it fails, an authenticated user must see a retry (not "log in"), and retrying
 * after the backend heals must load the profile. Exercises userStatus:'error' →
 * profileError → <Loadable> error slot → retryUserData().
 */
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { armFault, clearFaults } from './helpers/debugFaults';

test.describe('Resilience: profile load failure', () => {
    test.afterEach(async () => {
        await clearFaults();
    });

    test('shows Loadable retry when /auth/me fails, recovers on retry', async ({ page, testUsers }) => {
        await loginAsTestUser(page, testUsers.passwords.test);

        // Nuke the profile endpoint, then enter a profile-gated view (account-deletion
        // wraps its content in <Loadable error={$profileError}>).
        await armFault('/api/auth/me', { status: 500 });
        await page.goto('/account-deletion');

        // Authenticated but profile failed → Loadable shows the error/retry slot,
        // and we are NOT redirected to /login (the session is intact).
        const error = page.getByTestId('loadable-error');
        await expect(error).toBeVisible({ timeout: 15000 });
        expect(page.url()).not.toContain('/login');

        // Heal the backend, then retry.
        await clearFaults();
        await error.getByRole('button', { name: 'Retry' }).click();

        // Profile loads → the logged-in content renders.
        await expect(page.getByText(/logged in as/i)).toBeVisible({ timeout: 15000 });
        await expect(page.getByTestId('loadable-error')).toBeHidden();
    });
});
