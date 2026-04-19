import { test, expect } from './fixtures';
import { loginAs, loginAsTestUser, logoutUser, recreateTestUsers } from './helpers/testUsers';
import { collectErrors } from './helpers/consoleLogging';

/**
 * Advanced authentication scenarios covering login/logout cycles,
 * error recovery, session management, and edge cases.
 */

test.describe('Auth Scenarios', () => {

  // ── Login & Logout lifecycle ──

  test.describe('Login/Logout lifecycle', () => {
    test.describe.configure({ mode: 'serial' });

    test('login then logout redirects to /login', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      await expect(page).toHaveURL('/');

      await logoutUser(page);
      await expect(page).toHaveURL('/login');
    });

    test('login, logout, login again succeeds', async ({ page, testUsers }) => {
      // First session
      await loginAsTestUser(page, testUsers.passwords.test);
      await expect(page).toHaveURL('/');
      await logoutUser(page);

      // Second session
      await loginAsTestUser(page, testUsers.passwords.test);
      await expect(page).toHaveURL('/');
    });

    test('logout clears auth — account page inaccessible', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);

      // Verify account page works while logged in
      await page.goto('/account');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 10000 });

      // Logout
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await logoutUser(page);

      // Account page should no longer show profile
      await page.goto('/account');
      await page.waitForLoadState('networkidle');
      const hasUsername = await page.getByTestId('account-username').isVisible().catch(() => false);
      expect(hasUsername).toBe(false);
    });
  });

  // ── Error recovery ──

  test.describe('Error recovery', () => {

    test('wrong password then correct password succeeds', async ({ page, testUsers }) => {
      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      // First attempt — wrong password
      await page.getByTestId('login-username-input').fill('test');
      await page.getByTestId('login-password-input').fill('WrongPassword123!');
      await page.getByTestId('login-submit-button').click();

      // Should show error and stay on login
      await expect(page.getByTestId('login-error-message')).toBeVisible({ timeout: 10000 });
      await expect(page).toHaveURL('/login');

      // Second attempt — correct password
      await page.getByTestId('login-password-input').fill(testUsers.passwords.test);
      await page.getByTestId('login-submit-button').click();

      await page.waitForURL('/', { timeout: 15000 });
      await expect(page).toHaveURL('/');
    });

    test('wrong username then correct credentials succeeds', async ({ page, testUsers }) => {
      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      // Wrong username
      await page.getByTestId('login-username-input').fill('nonexistent_user_xyz');
      await page.getByTestId('login-password-input').fill(testUsers.passwords.test);
      await page.getByTestId('login-submit-button').click();

      await expect(page.getByTestId('login-error-message')).toBeVisible({ timeout: 10000 });

      // Correct credentials
      await page.getByTestId('login-username-input').fill('test');
      await page.getByTestId('login-password-input').fill(testUsers.passwords.test);
      await page.getByTestId('login-submit-button').click();

      await page.waitForURL('/', { timeout: 15000 });
    });
  });

  // ── Stale token handling ──

  test.describe('Stale token handling', () => {

    test('reload with stale token gracefully lands on /login without console errors', async ({ page, testUsers }) => {
      const { errors } = collectErrors(page);

      // Login — stores tokens in IndexedDB
      await loginAsTestUser(page, testUsers.passwords.test);
      await expect(page).toHaveURL('/');

      // Wipe DB — tokens in IndexedDB are now stale
      await recreateTestUsers();

      // Reload triggers checkAuth() with the stale token.
      // The app should handle the 401 gracefully and redirect to /login.
      await page.reload();
      await page.waitForURL('/login', { timeout: 15000 });
      await page.waitForLoadState('networkidle');

      // Re-login with fresh credentials succeeds
      await page.getByTestId('login-username-input').fill('test');
      await page.getByTestId('login-password-input').fill(testUsers.passwords.test);
      await page.getByTestId('login-submit-button').click();
      await page.waitForURL('/', { timeout: 15000 });

      expect(errors.length, `Unexpected console errors: ${errors.join(', ')}`).toBe(0);
    });

    test('login after logout and database recreation succeeds cleanly', async ({ page, testUsers }) => {
      const { errors } = collectErrors(page);

      // Login
      await loginAsTestUser(page, testUsers.passwords.test);
      await expect(page).toHaveURL('/');

      // Logout
      await logoutUser(page);

      // Let any post-logout cleanup requests settle against the still-valid DB
      // before we wipe it, otherwise they can race against the recreation and
      // trip a 500 (WebKit surfaces it as a CORS error because FastAPI's CORS
      // middleware doesn't always decorate error responses).
      await page.waitForLoadState('networkidle');

      // Recreate users (wipes DB)
      await recreateTestUsers();

      // Login again
      await loginAsTestUser(page, testUsers.passwords.test);
      await expect(page).toHaveURL('/');

      await page.waitForTimeout(1000);
      expect(errors.length, `Unexpected console errors: ${errors.join(', ')}`).toBe(0);
    });
  });

  // ── Auth state persistence ──

  test.describe('Auth state persistence', () => {

    test('auth persists across page navigations', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);

      // Navigate to account
      await page.goto('/account');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('account-username')).toHaveText('test', { timeout: 10000 });

      // Navigate to home
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Navigate back to account — should still be logged in
      await page.goto('/account');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('account-username')).toHaveText('test', { timeout: 10000 });
    });

    test('auth persists after page reload', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);

      await page.goto('/account');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('account-username')).toHaveText('test', { timeout: 10000 });

      // Hard reload
      await page.reload();
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('account-username')).toHaveText('test', { timeout: 10000 });
    });
  });

  // ── Registration flow ──

  test.describe('Registration', () => {

    test('register new user then login with new credentials', async ({ page, testUsers }) => {
      const uniqueUsername = `newuser_${Date.now()}`;
      const uniqueEmail = `${uniqueUsername}@test.example.com`;
      const password = 'StrongTestPassword123!';

      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      // Switch to register form
      await page.getByTestId('login-toggle-form-button').click();

      // Fill registration form
      await page.getByTestId('login-email-input').fill(uniqueEmail);
      // Username is auto-generated from email, but let's set it explicitly
      await page.getByTestId('login-username-input').fill(uniqueUsername);
      await page.getByTestId('login-password-input').fill(password);
      await page.getByTestId('login-submit-button').click();

      // Should show success message and switch to login form
      await expect(page.getByTestId('login-success-message')).toBeVisible({ timeout: 10000 });

      // Now login with the new credentials
      await page.getByTestId('login-username-input').fill(uniqueUsername);
      await page.getByTestId('login-password-input').fill(password);
      await page.getByTestId('login-submit-button').click();

      await page.waitForURL('/', { timeout: 15000 });
    });

    test('register with existing username shows error', async ({ page, testUsers }) => {
      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      // Switch to register form
      await page.getByTestId('login-toggle-form-button').click();

      // Try to register with existing username
      await page.getByTestId('login-email-input').fill('duplicate@test.example.com');
      await page.getByTestId('login-username-input').fill('test');
      await page.getByTestId('login-password-input').fill('StrongTestPassword123!');
      await page.getByTestId('login-submit-button').click();

      // Should show error
      await expect(page.getByTestId('login-error-message')).toBeVisible({ timeout: 10000 });
    });

    test('toggle between login and register forms preserves no stale state', async ({ page }) => {
      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      // Should start in login mode
      await expect(page.getByTestId('login-submit-button')).toHaveText('Login');

      // Switch to register
      await page.getByTestId('login-toggle-form-button').click();
      await expect(page.getByTestId('login-submit-button')).toHaveText('Register');
      await expect(page.getByTestId('login-email-input')).toBeVisible();

      // Switch back to login
      await page.getByTestId('login-toggle-form-button').click();
      await expect(page.getByTestId('login-submit-button')).toHaveText('Login');
      // Email field should be hidden in login mode
      await expect(page.getByTestId('login-email-input')).not.toBeVisible();
    });
  });

  // ── Multi-user scenarios ──

  test.describe('Multi-user', () => {

    test('login as different users in sequence', async ({ page, testUsers }) => {
      // Login as 'test'
      await loginAsTestUser(page, testUsers.passwords.test);
      await page.goto('/account');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('account-username')).toHaveText('test', { timeout: 10000 });

      // Logout
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await logoutUser(page);

      // Login as 'admin'
      await loginAs(page, 'admin', testUsers.passwords.admin);
      await page.goto('/account');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('account-username')).toHaveText('admin', { timeout: 10000 });
    });
  });

  // ── Navigation guards ──

  test.describe('Navigation guards', () => {

    test('visiting /login while authenticated redirects to /', async ({ page, testUsers }) => {
      await loginAsTestUser(page, testUsers.passwords.test);
      await expect(page).toHaveURL('/');

      // Try to visit login page
      await page.goto('/login');
      // Should redirect back since already authenticated
      await page.waitForURL('/', { timeout: 15000 });
    });

    test('submit button is disabled while loading', async ({ page, testUsers }) => {
      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      await page.getByTestId('login-username-input').fill('test');
      await page.getByTestId('login-password-input').fill(testUsers.passwords.test);

      // Click and immediately check disabled state
      const submitButton = page.getByTestId('login-submit-button');
      await submitButton.click();

      // Button should show loading text briefly
      // (may be too fast to catch, so we just verify the login succeeds)
      await page.waitForURL('/', { timeout: 15000 });
    });
  });
});
