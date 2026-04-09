import { test, expect } from './fixtures';

test.describe('Settings Pages', () => {
	test('should load settings page without errors', async ({ page }) => {
		await page.goto('/settings');
		await page.waitForLoadState('networkidle');

		// Advanced settings link should be visible
		await expect(page.getByTestId('advanced-menu-link')).toBeVisible({ timeout: 10000 });

		// Camera shutter toggle should be present
		await expect(page.getByTestId('shutter-sound-toggle')).toBeVisible();
	});

	test('should navigate to advanced settings', async ({ page }) => {
		await page.goto('/settings');
		await page.waitForLoadState('networkidle');

		await page.getByTestId('advanced-menu-link').click();
		await page.waitForURL('/settings/advanced', { timeout: 10000 });

		// Sources link should be visible on advanced page
		await expect(page.getByTestId('sources-menu-link')).toBeVisible({ timeout: 10000 });
	});

	test('should navigate to sources settings', async ({ page }) => {
		await page.goto('/settings/sources');
		await page.waitForLoadState('networkidle');

		// Built-in source toggles should be visible
		await expect(page.getByTestId('source-toggle-hillview')).toBeVisible({ timeout: 10000 });
		await expect(page.getByTestId('source-toggle-mapillary')).toBeVisible();
	});

	test('should toggle source checkboxes', async ({ page }) => {
		await page.goto('/settings/sources');
		await page.waitForLoadState('networkidle');

		// The checkbox input is visually hidden; click the visible label/toggle instead
		const hillviewToggle = page.getByTestId('source-toggle-hillview');
		await expect(hillviewToggle).toBeVisible({ timeout: 10000 });

		const hillviewCheckbox = page.getByTestId('source-checkbox-hillview');
		const initialState = await hillviewCheckbox.isChecked();

		// Toggle via the visible label
		await hillviewToggle.click();
		const newState = await hillviewCheckbox.isChecked();
		expect(newState).toBe(!initialState);

		// Toggle back
		await hillviewToggle.click();
		expect(await hillviewCheckbox.isChecked()).toBe(initialState);
	});
});
