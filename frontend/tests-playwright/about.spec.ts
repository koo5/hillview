import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { addCameraInitScript } from './helpers/cameraSetup';

test.describe('About page', () => {
	test('take-a-photo link navigates to the map and opens camera mode', async ({ page }) => {
		// Seed location/bearing so the capture view initializes cleanly
		await addCameraInitScript(page);

		await page.goto('/about');

		const link = page.getByTestId('about-take-photo-link');
		await expect(link).toBeVisible();
		await link.click();

		// Client-side navigation to the map with capture mode active
		await page.waitForURL((url) => url.pathname === '/', { timeout: T(15000) });
		await expect(page.getByTestId('camera-button')).toHaveClass(/active/, { timeout: T(15000) });
	});
});
