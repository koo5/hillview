import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';

test.describe('Navigation Menu', () => {
	test('should open menu and show core links', async ({ page }) => {
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Menu should not be visible initially
		await expect(page.getByTestId('nav-menu')).toBeHidden();

		// Open the menu
		await page.getByTestId('header-menu-button').click();
		await expect(page.getByTestId('nav-menu')).toBeVisible();

		// Core navigation links should be present
		await expect(page.getByTestId('my-photos-link')).toBeVisible();
		await expect(page.getByTestId('bestof-menu-link')).toBeVisible();
		await expect(page.getByTestId('nav-activity-link')).toBeVisible();
		await expect(page.getByTestId('nav-users-link')).toBeVisible();
		await expect(page.getByTestId('settings-menu-link')).toBeVisible();
	});

	test('should show login link when unauthenticated', async ({ page }) => {
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		await page.getByTestId('header-menu-button').click();
		await expect(page.getByTestId('nav-menu')).toBeVisible();

		await expect(page.getByTestId('nav-login-link')).toBeVisible();
		// Logout should not be visible
		await expect(page.getByTestId('nav-logout-button')).toBeHidden();
	});

	test('should show logout button when authenticated', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.getByTestId('header-menu-button').click();
		await expect(page.getByTestId('nav-menu')).toBeVisible();

		await expect(page.getByTestId('nav-logout-button')).toBeVisible();
		// Login link should not be visible
		await expect(page.getByTestId('nav-login-link')).toBeHidden();
	});

	test('should navigate to activity page', async ({ page }) => {
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		await page.getByTestId('header-menu-button').click();
		await page.getByTestId('nav-activity-link').click();

		await page.waitForURL('/activity', { timeout: 10000 });
	});

	test('should navigate to bestof page', async ({ page }) => {
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		await page.getByTestId('header-menu-button').click();
		await page.getByTestId('bestof-menu-link').click();

		await page.waitForURL('/bestof', { timeout: 10000 });
	});

	test('should logout and redirect to login', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		await page.getByTestId('header-menu-button').click();
		await page.getByTestId('nav-logout-button').click();

		await page.waitForURL('/login', { timeout: 15000 });
	});
});
