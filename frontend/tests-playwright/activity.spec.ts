import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';

test.describe('Activity Page', () => {
	test('should load without errors', async ({ page }) => {
		await page.goto('/activity');

		// Should show either activity list or empty state (no crash)
		const activityList = page.getByTestId('activity-list');
		const emptyState = page.getByTestId('activity-empty-state');
		const errorState = page.locator('.error');

		// The page renders twice (SSR list, then an onMount refetch that flips the
		// spinner back on), so poll for the settled state: loading gone AND either
		// the list or the empty state shown. (A one-shot wait can match the first
		// render and then race the refetch.)
		await expect.poll(async () =>
			(await page.getByTestId('activity-loading').isHidden()) &&
			((await activityList.isVisible()) || (await emptyState.isVisible())),
			{ timeout: T(15000) }
		).toBe(true);
		await expect(errorState).toBeHidden();
	});

	test('should show user groups when activity exists', async ({ page }) => {
		await page.goto('/activity');
		await expect(page.getByTestId('activity-loading')).toBeHidden({ timeout: T(15000) });

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

	test('each photo links to its crawlable /photo/<uid> permalink', async ({ page }) => {
		// SEO: /activity is server-rendered (web build) and an internal-link
		// path to fresh photo pages — every card's headline is a real
		// <a href="/photo/...">.
		await page.goto('/activity');
		await expect(page.getByTestId('activity-loading')).toBeHidden({ timeout: T(15000) });

		const activityList = page.getByTestId('activity-list');
		if (await activityList.isVisible().catch(() => false)) {
			const titleLinks = page.getByTestId('photo-item-title-link');
			await expect(titleLinks.first()).toBeVisible();
			expect(await titleLinks.first().getAttribute('href')).toMatch(/^\/photo\/.+/);
		}
	});
});
