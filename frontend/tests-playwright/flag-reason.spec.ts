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

test.describe('Flag reasons', () => {
	test('the actions menu offers reason choices that flag in one click', async ({ page, testUsers }) => {
		test.setTimeout(180_000);

		await loginAs(page, 'test', testUsers.passwords.test);
		await uploadPhoto(page, testPhotos[0]);
		await page.goto(MAP_URL);
		await ensureSourceEnabled(page, 'hillview', true);
		const photoId = await getFrontPhotoId(page);

		// The menu offers a default flag plus reason categories (no dialog).
		await page.locator('[data-testid="photo-actions-menu"]').click();
		await expect(page.getByTestId('menu-flag')).toBeVisible();
		await expect(page.getByTestId('menu-flag-geolocation')).toBeVisible();
		await expect(page.getByTestId('menu-flag-privacy')).toBeVisible();
		await expect(page.getByTestId('menu-flag-abuse')).toBeVisible();

		// Clicking a reason flags in one click — no separate step.
		await page.getByTestId('menu-flag-privacy').click();

		// The flag is recorded with that reason.
		const adminToken = await getUserToken('admin', testUsers.passwords.admin);
		const flags = await (await fetch(`${BACKEND_URL}/api/flagged/photos/all?photo_source=hillview&limit=200`, {
			headers: { Authorization: `Bearer ${adminToken}` },
		})).json();
		const flag = flags.find((f: any) => f.photo_id === photoId);
		expect(flag).toBeTruthy();
		expect(flag.reason).toBe('Privacy');
	});
});
