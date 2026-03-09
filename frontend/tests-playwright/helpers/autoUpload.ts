/**
 * Auto-upload configuration helpers for Playwright tests.
 *
 * After a browser-captured photo, the app shows a green "Configure auto-upload"
 * prompt. These helpers walk through the configuration flow:
 *   prompt → /settings/upload → license checkbox → enable radio → done
 */

import type { Page } from '@playwright/test';

/**
 * Wait for the auto-upload prompt and click "Configure auto-upload",
 * which navigates to /settings/upload.
 */
export async function clickConfigureAutoUpload(page: Page): Promise<void> {
	const prompt = page.locator('[data-testid="auto-upload-prompt"]');
	await prompt.waitFor({ state: 'visible', timeout: 15000 });

	await page.locator('[data-testid="configure-auto-upload"]').click();
	await page.waitForURL('**/settings/upload', { timeout: 10000 });
}

/**
 * On the /settings/upload page, accept the license and enable auto-upload.
 * Expects the page to already be on /settings/upload.
 */
export async function enableAutoUpload(page: Page): Promise<void> {
	const licenseCheckbox = page.locator('[data-testid="license-checkbox"]');
	await licenseCheckbox.waitFor({ state: 'visible', timeout: 10000 });
	if (!(await licenseCheckbox.isChecked())) {
		await licenseCheckbox.check();
	}

	const enabledRadio = page.locator('[data-testid="auto-upload-enabled"]');
	await enabledRadio.check();

	// Settings auto-save on radio change; wait for confirmation
	await page.locator('[data-testid="alert-message"]').waitFor({ state: 'visible', timeout: 5000 });
}

/**
 * Full flow: handle the auto-upload prompt after capture, configure settings.
 */
export async function configureAutoUploadFromPrompt(page: Page): Promise<void> {
	await clickConfigureAutoUpload(page);
	await enableAutoUpload(page);
}
