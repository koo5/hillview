import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';

/** Open the nav menu from any page (map uses hamburger-menu, other pages use header-menu-button). */
async function openMenu(page: import('@playwright/test').Page) {
	const menuButton = page.locator('[data-testid="header-menu-button"], [data-testid="hamburger-menu"]').first();
	await menuButton.click();
	await expect(page.getByTestId('nav-menu')).toBeVisible();
}

test.describe('Navigation Menu', () => {
	test('should open menu and show core links', async ({ page }) => {
		await page.goto('/bestof');
		await page.waitForLoadState('networkidle');

		// Menu should not be visible initially
		await expect(page.getByTestId('nav-menu')).toBeHidden();

		await openMenu(page);

		// Core navigation links should be present
		await expect(page.getByTestId('my-photos-link')).toBeVisible();
		await expect(page.getByTestId('bestof-menu-link')).toBeVisible();
		await expect(page.getByTestId('nav-activity-link')).toBeVisible();
		await expect(page.getByTestId('nav-users-link')).toBeVisible();
		await expect(page.getByTestId('settings-menu-link')).toBeVisible();
	});

	test('should show login link when unauthenticated', async ({ page }) => {
		await page.goto('/bestof');
		await page.waitForLoadState('networkidle');

		await openMenu(page);

		await expect(page.getByTestId('nav-login-link')).toBeVisible();
		await expect(page.getByTestId('nav-logout-button')).toBeHidden();
	});

	test('should show logout button when authenticated', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto('/bestof');
		await page.waitForLoadState('networkidle');

		await openMenu(page);

		await expect(page.getByTestId('nav-logout-button')).toBeVisible();
		await expect(page.getByTestId('nav-login-link')).toBeHidden();
	});

	test('should navigate to activity page', async ({ page }) => {
		await page.goto('/bestof');
		await page.waitForLoadState('networkidle');

		await openMenu(page);
		await page.getByTestId('nav-activity-link').click();

		await page.waitForURL('/activity', { timeout: 10000 });
	});

	test('should navigate to bestof page from settings', async ({ page }) => {
		await page.goto('/settings');
		await page.waitForLoadState('networkidle');

		await openMenu(page);
		await page.getByTestId('bestof-menu-link').click();

		await page.waitForURL('/bestof', { timeout: 10000 });
	});

	test('should logout and redirect to login', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.goto('/bestof');
		await page.waitForLoadState('networkidle');

		await openMenu(page);
		await page.getByTestId('nav-logout-button').click();

		await page.waitForURL('/login', { timeout: 15000 });
	});
});
