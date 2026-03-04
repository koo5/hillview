import { test as base } from '@playwright/test';

/**
 * Custom test fixtures applied to every Playwright test.
 *
 * Import { test, expect } from './fixtures' instead of '@playwright/test'.
 */
export const test = base.extend({
	page: async ({ page }, use) => {
		// Make every fake-camera capture produce unique pixel data so the
		// server-side duplicate-detection (MD5-based) never triggers across
		// captures within or between tests.
		await page.addInitScript(() => {
			let captureCounter = 0;
			const origDrawImage = CanvasRenderingContext2D.prototype.drawImage;
			CanvasRenderingContext2D.prototype.drawImage = function (...args: any[]) {
				origDrawImage.apply(this, args);
				if (args[0] instanceof HTMLVideoElement) {
					captureCounter++;
					this.fillStyle = 'rgba(255,255,255,0.01)';
					this.font = '10px monospace';
					this.fillText(`${captureCounter}-${Date.now()}`, 1, 10);
				}
			};
		});

		await use(page);
	},
});

export { expect } from '@playwright/test';
