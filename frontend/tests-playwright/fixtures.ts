import { test as base } from '@playwright/test';
import { createTestUsers, type TestUserSetupResult } from './helpers/testUsers';
import { setupConsoleLogging } from './helpers/consoleLogging';

/**
 * Track which spec file last triggered user recreation.
 * With workers: 1 and fullyParallel: false, this gives us
 * per-file isolation: users are recreated when a new spec
 * file starts, cascade-deleting photos/hidden_users/annotations
 * from the previous file.
 */
let lastSetupFile = '';
let cachedResult: TestUserSetupResult | null = null;

/**
 * Custom test fixtures applied to every Playwright test.
 *
 * Import { test, expect } from './fixtures' instead of '@playwright/test'.
 *
 * Available fixtures:
 *   testUsers - automatically recreates test users once per spec file.
 *               Provides { passwords, users_created, users_deleted }.
 */
export const test = base.extend<{ testUsers: TestUserSetupResult }>({
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

		// Relay browser console/errors to test output (gated by PLAYWRIGHT_CONSOLE_LOG env var)
		setupConsoleLogging(page);

		await use(page);
	},

	testUsers: [async ({}, use, testInfo) => {
		// Recreate test users once per spec file for isolation.
		// Subsequent tests within the same file reuse the cached result.
		if (testInfo.file !== lastSetupFile) {
			lastSetupFile = testInfo.file;
			cachedResult = await createTestUsers();
		}
		await use(cachedResult!);
	}, { auto: true }],
});

export { expect } from '@playwright/test';
