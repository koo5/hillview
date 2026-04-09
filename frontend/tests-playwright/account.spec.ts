import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';

test.describe('Account Page', () => {
	test('should display profile info for logged-in user', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto('/account');
		await page.waitForLoadState('networkidle');

		const profileCard = page.getByTestId('profile-card');
		await expect(profileCard).toBeVisible({ timeout: 10000 });

		// Username should match the logged-in user
		await expect(page.getByTestId('account-username')).toHaveText('test');

		// Action buttons should be visible
		await expect(page.getByTestId('account-logout-button')).toBeVisible();
		await expect(page.getByTestId('account-delete-button')).toBeVisible();
	});

	test('should open and cancel delete confirmation dialog', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto('/account');
		await page.waitForLoadState('networkidle');
		await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 10000 });

		// Open the delete dialog
		await page.getByTestId('account-delete-button').click();
		await expect(page.getByTestId('delete-confirm-modal')).toBeVisible();

		// Confirm button should be disabled without typing DELETE
		await expect(page.getByTestId('delete-confirm-button')).toBeDisabled();

		// Cancel closes the dialog
		await page.getByTestId('delete-cancel-button').click();
		await expect(page.getByTestId('delete-confirm-modal')).toBeHidden();
	});

	test('should keep confirm button disabled until DELETE is typed', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto('/account');
		await page.waitForLoadState('networkidle');
		await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 10000 });

		await page.getByTestId('account-delete-button').click();
		await expect(page.getByTestId('delete-confirm-modal')).toBeVisible();

		// Typing partial text keeps button disabled
		await page.getByTestId('delete-confirm-input').fill('DEL');
		await expect(page.getByTestId('delete-confirm-button')).toBeDisabled();

		// Typing DELETE enables the button
		await page.getByTestId('delete-confirm-input').fill('DELETE');
		await expect(page.getByTestId('delete-confirm-button')).toBeEnabled();
	});

	test('should redirect unauthenticated user away from account page', async ({ page }) => {
		await page.goto('/account');
		await page.waitForLoadState('networkidle');

		// Should show an error or redirect — profile card should not show user info
		const profileCard = page.getByTestId('profile-card');
		const errorMessage = page.locator('.error-message');

		// Either we see an error, or the profile card doesn't have a username
		const hasError = await errorMessage.isVisible().catch(() => false);
		const hasUsername = await page.getByTestId('account-username').isVisible().catch(() => false);

		expect(hasError || !hasUsername).toBeTruthy();
	});
});
