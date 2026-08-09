import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';

test.describe('Best Of Page', () => {
	test('should load without errors', async ({ page }) => {
		await page.goto('/bestof');

		// Should show either the photo grid or the empty state (no errors)
		const photoGrid = page.getByTestId('bestof-photo-grid');
		const emptyState = page.locator('.empty-state');
		const errorState = page.locator('.error');

		// The page renders twice (SSR, then an onMount refetch that flips the
		// spinner back on), so poll for the settled state: loading gone AND either
		// the grid or the empty state shown. (A one-shot wait can match the first
		// render and then race the refetch.)
		await expect.poll(async () =>
			(await page.locator('.loading-container').isHidden()) &&
			((await photoGrid.isVisible()) || (await emptyState.isVisible())),
			{ timeout: T(15000) }
		).toBe(true);

		// Should not show an error
		await expect(errorState).toBeHidden();
	});

	test('should show photo stats when photos exist', async ({ page }) => {
		await page.goto('/bestof');
		await expect(page.locator('.loading-container')).toBeHidden({ timeout: T(15000) });

		const photoGrid = page.getByTestId('bestof-photo-grid');
		if (await photoGrid.isVisible().catch(() => false)) {
			// Each card should have stats
			const cards = page.getByTestId('bestof-photo-card');
			const cardCount = await cards.count();
			expect(cardCount).toBeGreaterThan(0);

			// First card should have an annotation-count label
			await expect(cards.first().getByTestId('bestof-photo-stats')).toBeVisible();
			await expect(cards.first().getByTestId('bestof-photo-stats')).toContainText('annotation');
		}
	});

	test('each photo links to its crawlable /photo/<uid> permalink', async ({ page }) => {
		// SEO: photo pages must not be orphaned — the best-of grid is their
		// internal-link path for crawlers, so every card's headline is a real
		// <a href="/photo/..."> (rendered server-side in the web build).
		await page.goto('/bestof');
		await expect(page.locator('.loading-container')).toBeHidden({ timeout: T(15000) });

		const photoGrid = page.getByTestId('bestof-photo-grid');
		if (await photoGrid.isVisible().catch(() => false)) {
			const titleLinks = page.getByTestId('photo-item-title-link');
			await expect(titleLinks.first()).toBeVisible();
			expect(await titleLinks.first().getAttribute('href')).toMatch(/^\/photo\/.+/);
		}
	});
});
