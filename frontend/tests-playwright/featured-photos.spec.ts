import { test, expect } from './fixtures';
import { loginAsTestUser, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { BACKEND_URL } from './helpers/adminAuth';

// GPS location of the test photos
const TEST_PHOTO_MAP_URL = '/?lat=50.1153&lon=14.4938&zoom=18';

/** Set or unset the featured flag on a photo via the debug API. */
async function setFeatured(photoId: string, featured: boolean): Promise<void> {
	const res = await fetch(
		`${BACKEND_URL}/api/debug/set-featured?photo_id=${encodeURIComponent(photoId)}&featured=${featured}`,
		{ method: 'POST' },
	);
	if (!res.ok) throw new Error(`Failed to set featured: ${res.status}`);
}

/** Navigate to map at the test photo GPS coords with Hillview source enabled and wait for markers. */
async function goToMapWithMarkers(page: any): Promise<void> {
	await page.goto(TEST_PHOTO_MAP_URL);
	await page.waitForLoadState('networkidle');
	await ensureSourceEnabled(page, 'hillview', true);
	await page.waitForTimeout(3000); // wait for photos to load on map
}

/** Ensure hunter mode toggle is in the desired state. */
async function ensureHunterMode(page: any, desired: boolean): Promise<void> {
	const btn = page.locator('[data-testid="hunter-mode-toggle"]');
	const isActive = await btn.evaluate((el: HTMLElement) => el.classList.contains('active'));
	if (isActive !== desired) {
		await btn.click();
		await page.waitForTimeout(500);
	}
}

test.describe('Featured Photos', () => {
	test.describe.configure({ mode: 'serial' });

	let photoId1: string;
	let photoId2: string;

	test('setup: upload test photos', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAsTestUser(page, testUsers.passwords.test);
		photoId1 = await uploadPhoto(page, testPhotos[0]);
		photoId2 = await uploadPhoto(page, testPhotos[2]); // different GPS location to avoid marker overlap
		expect(photoId1).toBeTruthy();
		expect(photoId2).toBeTruthy();
	});

	test('hunter mode toggle is visible on map', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await goToMapWithMarkers(page);

		await expect(page.locator('[data-testid="hunter-mode-toggle"]')).toBeVisible();
	});

	test('featured marker gets gold color', async ({ page, testUsers }) => {
		await setFeatured(photoId1, true);

		await loginAsTestUser(page, testUsers.passwords.test);
		await goToMapWithMarkers(page);

		const featuredCircle = page.locator(`[data-photo-id="${photoId1}"] .bearing-circle`);
		await expect(featuredCircle).toBeVisible({ timeout: 10000 });

		const bgColor = await featuredCircle.evaluate(
			(el: HTMLElement) => el.style.backgroundColor,
		);
		expect(bgColor).toBe('gold');
	});

	test('non-featured markers are grayed when hunter mode is off', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await goToMapWithMarkers(page);
		await ensureHunterMode(page, false);

		// Non-featured marker should have .grayed class
		const nonFeaturedCircle = page.locator(`[data-photo-id="${photoId2}"] .bearing-circle`);
		await expect(nonFeaturedCircle).toBeVisible({ timeout: 10000 });
		await expect(nonFeaturedCircle).toHaveClass(/grayed/);

		// Featured marker should NOT have .grayed class
		const featuredCircle = page.locator(`[data-photo-id="${photoId1}"] .bearing-circle`);
		await expect(featuredCircle).not.toHaveClass(/grayed/);
	});

	test('toggling hunter mode removes grayed class', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await goToMapWithMarkers(page);
		await ensureHunterMode(page, false);

		const nonFeaturedCircle = page.locator(`[data-photo-id="${photoId2}"] .bearing-circle`);
		await expect(nonFeaturedCircle).toHaveClass(/grayed/);

		await ensureHunterMode(page, true);
		await expect(nonFeaturedCircle).not.toHaveClass(/grayed/);
	});

	test('clicking a grayed marker enables hunter mode', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await goToMapWithMarkers(page);
		await ensureHunterMode(page, false);

		// Click the grayed (non-featured) marker
		const nonFeaturedMarker = page.locator(`[data-photo-id="${photoId2}"]`);
		await nonFeaturedMarker.click();
		await page.waitForTimeout(500);

		// hunterMode should now be active
		const hunterToggle = page.locator('[data-testid="hunter-mode-toggle"]');
		await expect(hunterToggle).toHaveClass(/active/);

		// The clicked marker should no longer be grayed
		const circle = page.locator(`[data-photo-id="${photoId2}"] .bearing-circle`);
		await expect(circle).not.toHaveClass(/grayed/);
	});

	test('URL with featured photo auto-sets hunterMode off', async ({ page, testUsers }) => {
		await setFeatured(photoId1, true);
		await loginAsTestUser(page, testUsers.passwords.test);

		// Navigate via URL sharing a featured photo
		const photoUrl = `/?lat=50.1153&lon=14.4938&zoom=18&bearing=0&photo=hillview-${photoId1}`;
		await page.goto(photoUrl);
		await page.waitForLoadState('networkidle');

		// Hunter mode should be off because the URL photo is featured
		const hunterToggle = page.locator('[data-testid="hunter-mode-toggle"]');
		await expect(hunterToggle).not.toHaveClass(/active/, { timeout: 15000 });
	});

	test('URL with non-featured photo auto-sets hunterMode on', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);

		// Navigate via URL sharing a non-featured photo (photoId2 was never featured)
		const photoUrl = `/?lat=50.1153&lon=14.4938&zoom=18&bearing=0&photo=hillview-${photoId2}`;
		await page.goto(photoUrl);
		await page.waitForLoadState('networkidle');

		// Hunter mode should be on because the URL photo is not featured
		const hunterToggle = page.locator('[data-testid="hunter-mode-toggle"]');
		await expect(hunterToggle).toHaveClass(/active/, { timeout: 15000 });
	});

	test('unfeaturing all photos removes graying', async ({ page, testUsers }) => {
		await setFeatured(photoId1, false);

		await loginAsTestUser(page, testUsers.passwords.test);
		await goToMapWithMarkers(page);

		const grayedCircles = page.locator('.bearing-circle.grayed');
		await expect(grayedCircles).toHaveCount(0);
	});

	test.afterEach(async ({ page }) => {
		try { await logoutUser(page); } catch { /* ignore */ }
	});
});
