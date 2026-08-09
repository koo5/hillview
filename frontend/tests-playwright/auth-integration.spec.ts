import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';

test.describe('Authentication Integration', () => {
  test('should login successfully with valid credentials', async ({ page, testUsers }) => {
    await loginAsTestUser(page, testUsers.passwords.test);
    await expect(page).toHaveURL('/');
  });

  test('should show error for invalid username', async ({ page }) => {
    await page.goto('/login');

    await page.getByTestId('login-username-input').fill('invaliduser');
    await page.getByTestId('login-password-input').fill('anypassword');
    await page.getByTestId('login-submit-button').click();

    // Should stay on login page and show error
    await expect(page.getByTestId('login-error-message')).toBeVisible({ timeout: T(10000) });
    await expect(page).toHaveURL('/login');
  });

  test('should show error for invalid password', async ({ page }) => {
    await page.goto('/login');

    await page.getByTestId('login-username-input').fill('test');
    await page.getByTestId('login-password-input').fill('wrongpassword');
    await page.getByTestId('login-submit-button').click();

    // Should stay on login page and show error
    await expect(page.getByTestId('login-error-message')).toBeVisible({ timeout: T(10000) });
    await expect(page).toHaveURL('/login');
  });

  test('should show validation popup for empty credentials', async ({ page }) => {
    await page.goto('/login');

    const usernameInput = page.getByTestId('login-username-input');
    const passwordInput = page.getByTestId('login-password-input');

    // In dev mode (VITE_DEV_MODE=true, which the dev server used by these tests
    // runs with) the login form auto-fills test credentials. Clear them so we
    // actually exercise the empty-field required-attribute validation below
    // instead of submitting valid credentials and getting logged in.
    await usernameInput.fill('');
    await passwordInput.fill('');

    // Verify inputs have required attributes
    await expect(usernameInput).toHaveAttribute('required', '');
    await expect(passwordInput).toHaveAttribute('required', '');

    // Try to submit with empty fields - browser will show validation popup
    await page.getByTestId('login-submit-button').click();

    // Should stay on login page due to validation
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL('/login');

    // Verify that the form is still empty (validation prevented submission)
    await expect(usernameInput).toHaveValue('');
    await expect(passwordInput).toHaveValue('');
  });
});
