import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { getUserToken, BACKEND_URL } from './helpers/adminAuth';

type Page = import('@playwright/test').Page;

const MAP_URL = '/?lat=50.1153&lon=14.4938&zoom=18';

/** Read the id of the front gallery photo (waits for it to load). */
async function getFrontPhotoId(page: Page): Promise<string> {
	const mainPhoto = page.locator('[data-testid="main-photo"].front');
	await mainPhoto.waitFor({ state: 'visible', timeout: T(60000) });
	const data = await mainPhoto.evaluate((el) => JSON.parse(el.getAttribute('data-photo') || '{}'));
	return data.id as string;
}

test.describe('Flag reason dialog', () => {
	test('flagging opens a reason dialog with a default, presets and other-text', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		await loginAs(page, 'test', testUsers.passwords.test);
		await uploadPhoto(page, testPhotos[0]);
		await page.goto(MAP_URL);
		await ensureSourceEnabled(page, 'hillview', true);
		const photoId = await getFrontPhotoId(page);

		// One "Flag for Review" item opens the dialog (no reason submenu).
		await page.locator('[data-testid="photo-actions-menu"]').click();
		await page.locator('[data-testid="menu-flag"]').click();
		await expect(page.getByTestId('flag-reason-dialog')).toBeVisible();

		// Presets are offered and one is preselected by default.
		await expect(page.getByTestId('flag-reason-wrong-geolocation')).toBeChecked();
		await expect(page.getByTestId('flag-reason-privacy')).toBeVisible();
		await expect(page.getByTestId('flag-reason-abuse-spam')).toBeVisible();

		// "Other" reveals a text field; the entered text becomes the reason.
		await page.getByTestId('flag-reason-other').check();
		await page.getByTestId('flag-reason-other-text').fill('Duplicate upload');
		await page.getByTestId('flag-reason-confirm').click();
		await expect(page.getByTestId('flag-reason-dialog')).not.toBeVisible({ timeout: T(10000) });

		// The flag is recorded with the chosen reason.
		const adminToken = await getUserToken('admin', testUsers.passwords.admin);
		const flags = await (await fetch(`${BACKEND_URL}/api/flagged/photos/all?photo_source=hillview&limit=200`, {
			headers: { Authorization: `Bearer ${adminToken}` },
		})).json();
		const flag = flags.find((f: any) => f.photo_id === photoId);
		expect(flag).toBeTruthy();
		expect(flag.reason).toBe('Duplicate upload');
	});
});
