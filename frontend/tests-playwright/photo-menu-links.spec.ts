import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { createMockMapillaryData, setupMockMapillaryData, clearMockMapillaryData } from './helpers/mapillaryMocks';
import { configureSources } from './helpers/sourceHelpers';
import { setMapLocation } from './helpers/mapSetup';

/**
 * Regression tests for the PhotoActionsMenu link behavior:
 *   - Navigating menu items (user-profile, captured-at) render as real <a>
 *     elements with an href, so middle-click / ctrl-click get native
 *     open-in-new-tab behavior.
 *   - Plain left-click dispatches exactly one navigation (either SPA goto
 *     or openExternalUrl), never both at the same time.
 *   - For Mapillary photos the captured-at link points to mapillary.com,
 *     not the internal Hillview detail page.
 */

async function openGalleryPhotoMenu(page: any) {
	await page.goto('/');
	await page.waitForLoadState('networkidle');
	await page.waitForSelector('.leaflet-container', { timeout: 10000 });
	// PhotoActionsMenu is only attached to the front photo in the gallery.
	const menuTrigger = page.locator('[data-testid="photo-actions-menu"]');
	await menuTrigger.first().waitFor({ state: 'visible', timeout: 15000 });
	await menuTrigger.first().click();
	await page.locator('[data-testid="photo-actions-dropdown"]').waitFor({ state: 'visible', timeout: 5000 });
}

test.describe('Photo actions menu — link semantics', () => {
	test('Hillview photo: url menu items render as <a> with correct href', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await uploadPhoto(page, testPhotos[0]);

		await openGalleryPhotoMenu(page);

		const userProfile = page.locator('[data-testid="menu-user-profile"]');
		await expect(userProfile).toBeVisible();
		await expect(userProfile).toHaveJSProperty('tagName', 'A');
		expect(await userProfile.getAttribute('href')).toMatch(/^\/users\/[^/]+$/);

		const capturedAt = page.locator('[data-testid="menu-captured-at"]');
		await expect(capturedAt).toBeVisible();
		await expect(capturedAt).toHaveJSProperty('tagName', 'A');
		expect(await capturedAt.getAttribute('href')).toMatch(/^\/photo\/hillview-/);
	});

	test('left-click on a url item navigates in-app exactly once', async ({ page, context, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await uploadPhoto(page, testPhotos[0]);

		await openGalleryPhotoMenu(page);

		const item = page.locator('[data-testid="menu-user-profile"]');
		const href = await item.getAttribute('href');
		expect(href).toMatch(/^\/users\//);

		const pagesBefore = context.pages().length;
		let strayTabOpened = false;
		const onPage = () => { strayTabOpened = true; };
		context.on('page', onPage);

		await item.click();

		// Current page SPA-navigates to /users/<id>.
		await page.waitForURL(/\/users\/[^/]+$/);

		// Give any stray tab a chance to appear (regression guard against
		// both onclick AND anchor default firing).
		await page.waitForTimeout(300);
		context.off('page', onPage);

		expect(strayTabOpened).toBe(false);
		expect(context.pages().length).toBe(pagesBefore);
	});

	test('middle-click on a url item does not navigate the current page', async ({ page, testUsers }) => {
		await loginAsTestUser(page, testUsers.passwords.test);
		await uploadPhoto(page, testPhotos[0]);

		await openGalleryPhotoMenu(page);

		const item = page.locator('[data-testid="menu-user-profile"]');
		const urlBefore = page.url();

		await item.click({ button: 'middle' });

		// The current page must not navigate — middle-click is handled by the
		// browser (new tab) or ignored, but never by our SPA goto.
		await page.waitForTimeout(500);
		expect(page.url()).toBe(urlBefore);
	});

	test('Mapillary photo: captured-at item links to mapillary.com, not /photo/<uid>', async ({ page }) => {
		// Seed 15 mock Mapillary photos at a known point and pin the map there,
		// then enable only the Mapillary source so the front photo is Mapillary.
		await clearMockMapillaryData(page);
		const centerLat = 50.114;
		const centerLng = 14.523;
		const mockData = createMockMapillaryData(centerLat, centerLng);
		await setupMockMapillaryData(page, mockData);

		await page.goto('/');
		await page.waitForLoadState('networkidle');
		await page.waitForSelector('.leaflet-container', { timeout: 10000 });
		await setMapLocation(page, centerLat, centerLng, 16);
		await configureSources(page, { hillview: false, device: false, mapillary: true });
		await page.waitForSelector('[data-testid="main-photo"]', { timeout: 20000 });

		// Sanity-check the front photo's source is mapillary.
		const source = await page
			.locator('[data-testid="main-photo"]')
			.first()
			.evaluate((el: Element) => {
				const data = JSON.parse(el.getAttribute('data-photo') || '{}');
				return data?.source?.id ?? data?.source;
			});
		expect(source).toBe('mapillary');

		const menuTrigger = page.locator('[data-testid="photo-actions-menu"]').first();
		await menuTrigger.waitFor({ state: 'visible', timeout: 10000 });
		await menuTrigger.click();
		await page.locator('[data-testid="photo-actions-dropdown"]').waitFor({ state: 'visible', timeout: 5000 });

		const item = page.locator('[data-testid="menu-captured-at"]');
		await expect(item).toBeVisible();
		await expect(item).toHaveJSProperty('tagName', 'A');
		const href = await item.getAttribute('href');
		expect(href).toMatch(/^https:\/\/www\.mapillary\.com\/app\/\?pKey=/);

		await clearMockMapillaryData(page);
	});
});
