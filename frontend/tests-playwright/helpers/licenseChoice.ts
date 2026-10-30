import { expect, type Locator, type Page } from '@playwright/test';

export async function confirmLicenseChoice(page: Page, grant: string) {
	const dialog = page.getByTestId('license-dialog');
	await expect(dialog).toBeVisible();
	await dialog.getByTestId(grant === 'ccbysa4+osm' ? 'license-checkbox' : `license-option-${grant}`).check();
	await dialog.getByTestId('license-dialog-confirm').click();
	await expect(dialog).toHaveCount(0);
}

export async function chooseUploadLicense(page: Page, grant = 'ccbysa4+osm', trigger?: Locator) {
	await (trigger ?? page.getByTestId('license-change-button')).click();
	await confirmLicenseChoice(page, grant);
}
