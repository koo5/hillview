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

		// Force a known tourist start (selecting the front photo may already have
		// enabled hunter) so the open→hunter, close→tourist round-trip is observable.
		const hunterToggle = page.getByTestId('hunter-mode-toggle');
		if ((await hunterToggle.getAttribute('class') ?? '').includes('active')) {
			await hunterToggle.click();
		}
		await expect(hunterToggle).not.toHaveClass(/active/);
		// The front photo stays selected in tourist mode (no featured photos here).
		await expect(page.locator('.bearing-circle.selected')).toBeVisible({ timeout: 11 * 10000 });

		// 't' toggles the timeline open for the current front photo.
		await page.keyboard.press('t');

		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });

		// Opening the walk takes over hunter mode — its photos are mostly
		// non-featured, so they need it to stay navigable.
		await expect(hunterToggle).toHaveClass(/active/);

		// The list populates from the timeline endpoint with the uploaded photos.
		const rows = page.getByTestId('timeline-row');
		await expect(rows.first()).toBeVisible({ timeout: 11 * 15000 });
		expect(await rows.count()).toBeGreaterThanOrEqual(2);

		// Opens narrow by default (thumbnails-only; add-user collapses to "+").
		await expect(panel).toHaveClass(/narrow/);
		await expect(page.getByTestId('timeline-add-user')).toHaveText('+');
		// Width toggle → wide.
		await page.getByTestId('timeline-width-toggle').click();
		await expect(panel).not.toHaveClass(/narrow/);
		// The anchor's owner (the test user) is listed in the tracked users.
		// (The users section is only shown in wide mode.)
		await expect(page.getByTestId('timeline-user').first()).toBeVisible();
		// Toggle back → narrow.
		await page.getByTestId('timeline-width-toggle').click();
		await expect(panel).toHaveClass(/narrow/);

		// 't' again toggles it closed.
		await page.keyboard.press('t');
		await expect(panel).toBeHidden({ timeout: 11 * 10000 });

		// Closing restores the tourist mode we forced before opening.
		await expect(hunterToggle).not.toHaveClass(/active/);
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

	test('add-user picker adds and removes a tracked user', async ({ page, testUsers }) => {
		test.setTimeout(120_000);
		await openMapWithFrontPhoto(page, testUsers.passwords.test);

		await page.keyboard.press('t');
		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });

		// Starts with exactly one tracked user (the anchor's owner), shown by name.
		await expect(page.getByTestId('timeline-user')).toHaveCount(1, { timeout: 11 * 15000 });

		// Open the picker and wait for the user list to load.
		await page.getByTestId('timeline-add-user').click();
		await expect(page.getByTestId('timeline-user-picker')).toBeVisible();
		const options = page.getByTestId('timeline-user-option');
		await expect(options.first()).toBeVisible({ timeout: 11 * 15000 });

		// Adding one → two tracked users; the picker closes.
		await options.first().click();
		await expect(page.getByTestId('timeline-user')).toHaveCount(2, { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-user-picker')).toBeHidden();

		// Removing the added one → back to one.
		await page.getByTestId('timeline-user-remove').last().click();
		await expect(page.getByTestId('timeline-user')).toHaveCount(1, { timeout: 11 * 15000 });
	});

	test('content filters narrow the walk, and it reloads live while open', async ({ page, testUsers }) => {
		test.setTimeout(120_000);
		await openMapWithFrontPhoto(page, testUsers.passwords.test);

		// Open the walk; the uploaded test photos are unanalyzed, so they all list.
		// Opening also enables hunter mode, which reveals the bottom bar — that's
		// why the filters button below is clickable (the panel now stops above it).
		await page.keyboard.press('t');
		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });
		const rows = page.getByTestId('timeline-row');
		await expect(rows.first()).toBeVisible({ timeout: 11 * 15000 });
		expect(await rows.count()).toBeGreaterThanOrEqual(2);
		const status = page.getByTestId('timeline-status');

		// Apply a content filter and turn OFF show-unanalyzed. Unlike the map (which
		// keeps unanalyzed photos, just grayed), the walk hard-excludes them — and it
		// reloads live while the panel stays open.
		await page.getByTestId('filters-button').click();
		const modal = page.getByTestId('filters-modal');
		await expect(modal).toBeVisible();
		await modal.locator('[data-testid="filter"][data-filter-name="time_of_day"][data-filter-value="day"]').click();
		await modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]').uncheck();
		await modal.locator('.close-button').click();

		// The walk empties — every uploaded photo is unanalyzed.
		await expect(status).toHaveText('No photos', { timeout: 11 * 15000 });
		await expect(rows).toHaveCount(0);

		// Re-enabling show-unanalyzed brings the walk back (live reload again).
		await page.getByTestId('filters-button').click();
		await expect(modal).toBeVisible();
		await modal.locator('[data-testid="show-unanalyzed"] input[type="checkbox"]').check();
		await modal.locator('.close-button').click();

		await expect(rows.first()).toBeVisible({ timeout: 11 * 15000 });
		expect(await rows.count()).toBeGreaterThanOrEqual(2);
	});

	test('leaving hunter mode closes the walk and stays in tourist', async ({ page, testUsers }) => {
		test.setTimeout(120_000);
		await openMapWithFrontPhoto(page, testUsers.passwords.test);
		const hunterToggle = page.getByTestId('hunter-mode-toggle');

		await page.keyboard.press('t');
		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });
		await expect(hunterToggle).toHaveClass(/active/);  // opening forced hunter on

		// Hunter mode is an invariant of an open walk — turning it off exits the walk
		// and honours the choice (we don't bounce back into hunter on close).
		await hunterToggle.click();
		await expect(panel).toBeHidden({ timeout: 11 * 10000 });
		await expect(hunterToggle).not.toHaveClass(/active/);
	});
});
