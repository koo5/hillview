import { test, expect } from './fixtures';

async function waitForMap(page: import('@playwright/test').Page) {
	await page.goto('/');
	await page.waitForSelector('.leaflet-container', { timeout: 10000 });
	await page.waitForTimeout(2000);
	await expect(page.locator('.leaflet-container')).toBeVisible();
}

test.describe('Compass menu interactions', () => {
	test('desktop: clicking the button closes an open compass menu', async ({ page }) => {
		await waitForMap(page);

		const compassButton = page.getByTestId('compass-button');
		const dropdownTrigger = page.locator('[data-testid="compass-button"] .dropdown-trigger');
		const menu = page.getByTestId('compass-mode-menu');

		await expect(compassButton).toBeVisible();
		await expect(dropdownTrigger).toBeVisible();

		await dropdownTrigger.click();
		await expect(menu).toBeVisible();

		await compassButton.click();
		await expect(menu).toBeHidden();
	});

	test('mobile parity: tapping the button closes an open compass menu', async ({ browser }) => {
		const context = await browser.newContext({
			hasTouch: true,
			isMobile: true,
			viewport: { width: 375, height: 667 }
		});
		const page = await context.newPage();

		try {
			await waitForMap(page);

			const compassButton = page.getByTestId('compass-button');
			const menu = page.getByTestId('compass-mode-menu');

			await expect(compassButton).toBeVisible();

			await compassButton.dispatchEvent('pointerdown', {
				button: 0,
				pointerType: 'touch',
				isPrimary: true
			});
			await page.waitForTimeout(550);
			await compassButton.dispatchEvent('pointerup', {
				button: 0,
				pointerType: 'touch',
				isPrimary: true
			});
			await expect(menu).toBeVisible();

			await compassButton.dispatchEvent('pointerdown', {
				button: 0,
				pointerType: 'touch',
				isPrimary: true
			});
			await compassButton.dispatchEvent('pointerup', {
				button: 0,
				pointerType: 'touch',
				isPrimary: true
			});
			await expect(menu).toBeHidden();
		} finally {
			await context.close();
		}
	});
});

