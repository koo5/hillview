import { test, expect } from './fixtures';
import { loginAsTestUser, logoutUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { BACKEND_URL } from './helpers/adminAuth';
import { setMapLocation } from './helpers/mapSetup';

// GPS location of the test photos (~50.1153, 14.4938)
const TEST_PHOTO_LAT = 50.1153;
const TEST_PHOTO_LNG = 14.4938;

/** Set or unset the featured flag on a photo via the debug API. */
async function setFeatured(photoId: string, featured: boolean): Promise<void> {
	const res = await fetch(
		`${BACKEND_URL}/api/debug/set-featured?photo_id=${encodeURIComponent(photoId)}&featured=${featured}`,
		{ method: 'POST' },
	);
	if (!res.ok) throw new Error(`Failed to set featured for ${photoId}: ${res.status}`);
}

/** Get all visible photo marker IDs on the map. */
async function getVisibleMarkerIds(page: any): Promise<string[]> {
	return page.evaluate(() => {
		const markers = document.querySelectorAll('.marker-container[data-photo-id]');
		return Array.from(markers).map(m => m.getAttribute('data-photo-id')).filter(Boolean);
	});
}

test.describe('Picks Persistence', () => {
	test.describe.configure({ mode: 'serial' });

	// Photo IDs populated in setup
	const photoIds: string[] = [];

	test('setup: upload 4 test photos', async ({ page, testUsers }) => {
		test.setTimeout(240_000);
		await loginAsTestUser(page, testUsers.passwords.test);
		for (const filename of testPhotos) {
			const id = await uploadPhoto(page, filename);
			expect(id).toBeTruthy();
			photoIds.push(id);
			console.log(`Uploaded ${filename} → ${id}`);
		}
		expect(photoIds).toHaveLength(4);
	});

	test('picked photo marker persists through area update when featured photos fill quota', async ({ page, testUsers }) => {
		test.setTimeout(120_000);

		// Pre-seed localStorage BEFORE navigating to the app:
		// maxPhotosInArea=3 so backend only returns 3 photos per area query
		await page.addInitScript(() => {
			localStorage.setItem('maxPhotosInArea', '3');
		});

		await loginAsTestUser(page, testUsers.passwords.test);

		// Navigate to the test photo GPS coords
		await page.goto(`/?lat=${TEST_PHOTO_LAT}&lon=${TEST_PHOTO_LNG}&zoom=18`);
		await page.waitForLoadState('networkidle');

		// Enable hillview source and wait for markers
		await ensureSourceEnabled(page, 'hillview', true);
		await page.waitForFunction(() => {
			return document.querySelectorAll('.marker-container[data-photo-id]').length > 0;
		}, { timeout: 30000 });
		await page.waitForTimeout(2000); // let things settle

		// Read which markers are visible — should be 3 out of 4
		const initialMarkerIds = await getVisibleMarkerIds(page);
		console.log(`Initial markers: ${initialMarkerIds.join(', ')}`);
		expect(initialMarkerIds.length).toBeGreaterThanOrEqual(1);
		expect(initialMarkerIds.length).toBeLessThanOrEqual(3);

		// The app auto-selects a front photo (the pick) — read its ID from the selected marker
		const selectedId = await page.evaluate(() => {
			const selected = document.querySelector('.bearing-circle.selected');
			return selected?.closest('.marker-container')?.getAttribute('data-photo-id') || null;
		});
		expect(selectedId).toBeTruthy();
		const pickId = selectedId!;
		console.log(`Front photo (auto-selected pick): ${pickId}`);

		// Mark all OTHER photos as featured.
		// On the next area update, the backend prioritizes featured photos.
		// With max_photos=3, only featured photos fill the quota.
		// The picked photo (non-featured) would be dropped WITHOUT picks support.
		const otherIds = photoIds.filter(id => id !== pickId);
		expect(otherIds.length).toBe(3);
		for (const id of otherIds) {
			await setFeatured(id, true);
			console.log(`Marked ${id} as featured`);
		}

		// Pan the map slightly to trigger an area update
		await setMapLocation(page, TEST_PHOTO_LAT + 0.0001, TEST_PHOTO_LNG + 0.0001, 18);
		console.log('Panned map to trigger area update');

		// Wait for the area update to complete and photos to reload
		await page.waitForTimeout(5000);

		// The picked photo's marker should still be on the map
		// because it was sent as a pick to the backend via the URL params
		const markerAfterPan = page.locator(`[data-photo-id="${pickId}"]`);
		await expect(markerAfterPan).toBeVisible({ timeout: 10000 });

		// Verify the marker is still among the visible markers
		const markersAfterPan = await getVisibleMarkerIds(page);
		console.log(`Markers after pan: ${markersAfterPan.join(', ')}`);
		expect(markersAfterPan).toContain(pickId);
	});

	test.afterEach(async ({ page }) => {
		// Clean up featured flags
		for (const id of photoIds) {
			try { await setFeatured(id, false); } catch { /* ignore */ }
		}
		try { await logoutUser(page); } catch { /* ignore */ }
	});
});
