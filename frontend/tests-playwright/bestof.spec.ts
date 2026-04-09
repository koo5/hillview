import { test, expect } from './fixtures';

test.describe('Best Of Page', () => {
	test('should load without errors', async ({ page }) => {
		await page.goto('/bestof');
		await page.waitForLoadState('networkidle');

		// Should show either the photo grid or the empty state (no errors)
		const photoGrid = page.getByTestId('bestof-photo-grid');
		const emptyState = page.locator('.empty-state');
		const errorState = page.locator('.error');

		// Wait for loading to finish
		await expect(page.locator('.loading-container')).toBeHidden({ timeout: 15000 });

		// Should not show an error
		await expect(errorState).toBeHidden();

		// Should show either photos or empty state
		const hasPhotos = await photoGrid.isVisible().catch(() => false);
		const isEmpty = await emptyState.isVisible().catch(() => false);
		expect(hasPhotos || isEmpty).toBeTruthy();
	});

	test('should show photo scores when photos exist', async ({ page }) => {
		await page.goto('/bestof');
		await page.waitForLoadState('networkidle');
		await expect(page.locator('.loading-container')).toBeHidden({ timeout: 15000 });

		const photoGrid = page.getByTestId('bestof-photo-grid');
		if (await photoGrid.isVisible().catch(() => false)) {
			// Each card should have a score
			const cards = page.getByTestId('bestof-photo-card');
			const cardCount = await cards.count();
			expect(cardCount).toBeGreaterThan(0);

			// First card should have a score label
			await expect(cards.first().getByTestId('bestof-photo-score')).toBeVisible();
		}
	});
});
