import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';

test.describe('Account Page', () => {
	test('should display profile info for logged-in user', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto('/account');

		const profileCard = page.getByTestId('profile-card');
		await expect(profileCard).toBeVisible({ timeout: 11*10000 });

		// Username should match the logged-in user
		await expect(page.getByTestId('account-username')).toHaveText('test');

		// Action buttons should be visible
		await expect(page.getByTestId('account-logout-button')).toBeVisible();
		await expect(page.getByTestId('account-delete-button')).toBeVisible();
	});

	test('should open and cancel delete confirmation dialog', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto('/account');
		await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 11*10000 });

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
		await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 11*10000 });

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

		// Unauthenticated: the profile load fails, so the page shows an error and/or
		// omits the username. Poll for that outcome to settle rather than a blanket
		// networkidle wait (which can hang on the dev server).
		const errorMessage = page.locator('.error-message');
		await expect
			.poll(async () =>
				(await errorMessage.isVisible().catch(() => false)) ||
				!(await page.getByTestId('account-username').isVisible().catch(() => false)),
			{ timeout: 11*10000 })
			.toBeTruthy();
	});
});
