import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';

// GPS location of the test photos (~50.1153, 14.4938)
const TEST_PHOTO_LAT = 50.1153;
const TEST_PHOTO_LNG = 14.4938;

/** Load the map at the test photos and wait until a front photo is auto-selected
 *  (that front photo is the anchor the timeline walks from). */
async function openMapWithFrontPhoto(page: any, password: string) {
	await loginAsTestUser(page, password);
	await page.goto(`/?lat=${TEST_PHOTO_LAT}&lon=${TEST_PHOTO_LNG}&zoom=18`);
	await page.waitForLoadState('networkidle');
	await ensureSourceEnabled(page, 'hillview', true);
	await page.waitForFunction(
		() => document.querySelectorAll('.marker-container[data-photo-id]').length > 0,
		{ timeout: 11 * 30000 },
	);
	await page.waitForFunction(
		() => !!document.querySelector('.bearing-circle.selected'),
		{ timeout: 11 * 15000 },
	);
}

test.describe('Timeline walk', () => {
	test.describe.configure({ mode: 'serial' });

	test('setup: upload 3 test photos', async ({ page, testUsers }) => {
		test.setTimeout(240_000);
		await loginAsTestUser(page, testUsers.passwords.test);
		for (const filename of testPhotos.slice(0, 3)) {
			const id = await uploadPhoto(page, filename);
			expect(id).toBeTruthy();
		}
	});

	test('t opens the timeline panel, lists photos, toggles width, and closes', async ({ page, testUsers }) => {
		test.setTimeout(120_000);
		await openMapWithFrontPhoto(page, testUsers.passwords.test);

		// 't' toggles the timeline open for the current front photo.
		await page.keyboard.press('t');

		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });

		// The list populates from the timeline endpoint with the uploaded photos.
		const rows = page.getByTestId('timeline-row');
		await expect(rows.first()).toBeVisible({ timeout: 11 * 15000 });
		expect(await rows.count()).toBeGreaterThanOrEqual(2);

		// The anchor's owner (the test user) is listed in the tracked users.
		await expect(page.getByTestId('timeline-user').first()).toBeVisible();

		// Width toggle → narrow (thumbnails-only; add-user collapses to "+").
		await page.getByTestId('timeline-width-toggle').click();
		await expect(panel).toHaveClass(/narrow/);
		await expect(page.getByTestId('timeline-add-user')).toHaveText('+');
		// Toggle back → wide.
		await page.getByTestId('timeline-width-toggle').click();
		await expect(panel).not.toHaveClass(/narrow/);

		// 't' again toggles it closed.
		await page.keyboard.press('t');
		await expect(panel).toBeHidden({ timeout: 11 * 10000 });
	});

	test('jumping a row and stepping with . / , move the cursor', async ({ page, testUsers }) => {
		test.setTimeout(120_000);
		await openMapWithFrontPhoto(page, testUsers.passwords.test);

		await page.keyboard.press('t');
		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });

		const rows = page.getByTestId('timeline-row');
		await expect(rows.first()).toBeVisible({ timeout: 11 * 15000 });
		const n = await rows.count();
		expect(n).toBeGreaterThanOrEqual(2);

		const status = page.getByTestId('timeline-status');

		// Jump to the oldest (first) row → "1 / n". The cursor is set synchronously,
		// independent of the map fly/selection, so the status is deterministic.
		await rows.first().click();
		await expect(status).toHaveText(`1 / ${n}`, { timeout: 11 * 10000 });

		// '.' steps to the next (newer) photo → "2 / n".
		await page.keyboard.press('.');
		await expect(status).toHaveText(`2 / ${n}`, { timeout: 11 * 10000 });

		// ',' steps back → "1 / n".
		await page.keyboard.press(',');
		await expect(status).toHaveText(`1 / ${n}`, { timeout: 11 * 10000 });
	});
});
