import { test, expect } from './fixtures';

test.describe('Activity Page', () => {
	test('should load without errors', async ({ page }) => {
		await page.goto('/activity');
		await page.waitForLoadState('networkidle');

		// Wait for loading to finish
		await expect(page.getByTestId('activity-loading')).toBeHidden({ timeout: 15000 });

		// Should show either activity list or empty state (no crash)
		const activityList = page.getByTestId('activity-list');
		const emptyState = page.getByTestId('activity-empty-state');
		const errorState = page.locator('.error');

		await expect(errorState).toBeHidden();

		const hasList = await activityList.isVisible().catch(() => false);
		const isEmpty = await emptyState.isVisible().catch(() => false);
		expect(hasList || isEmpty).toBeTruthy();
	});

	test('should show user groups when activity exists', async ({ page }) => {
		await page.goto('/activity');
		await page.waitForLoadState('networkidle');
		await expect(page.getByTestId('activity-loading')).toBeHidden({ timeout: 15000 });

		const activityList = page.getByTestId('activity-list');
		if (await activityList.isVisible().catch(() => false)) {
			// Should have at least one day group with a date header
			const dayGroups = page.locator('.day-group');
			expect(await dayGroups.count()).toBeGreaterThan(0);

			// Should have at least one username link
			const usernameLinks = page.locator('.username-link');
			expect(await usernameLinks.count()).toBeGreaterThan(0);
		}
	});
});
