import { test, expect } from '@playwright/test';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';
import { setupConsoleLogging } from './helpers/consoleLogging';
import {
	getPhotoCount,
	waitForPhotoCount,
	getLatestPhoto,
	waitForUploadedCount,
	getAllPhotosDetailed
} from './helpers/indexedDbPhotos';

// Pre-seed localStorage so camera button is visible and location data is available
function addCameraInitScript(page: any) {
	return page.addInitScript(() => {
		localStorage.setItem('appSettings', JSON.stringify({
			debug: 0,
			debug_enabled: true,
			activity: 'view'
		}));
		localStorage.setItem('spatialState', JSON.stringify({
			center: { lat: 50.11692, lng: 14.48837 },
			zoom: 20,
			bounds: null,
			range: 1000,
			source: 'map'
		}));
		localStorage.setItem('bearingState', JSON.stringify({
			bearing: 141,
			source: 'map',
			accuracy_level: null
		}));
	});
}

test.describe('Browser Capture → Upload', () => {
	test.describe.configure({ mode: 'serial' });

	let testPasswords: any;

	test.beforeAll(async () => {
		const result = await createTestUsers();
		testPasswords = result.passwords;
	});

	test.beforeEach(async ({ page, browserName }) => {
		test.skip(browserName !== 'chromium', 'Fake camera only works in Chromium');
		setupConsoleLogging(page);
		await addCameraInitScript(page);
	});

	test('capture photo before login, login triggers auto-upload, photo appears on server', async ({ page }) => {
		// Navigate to main page (not logged in)
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Open camera
		const cameraButton = page.locator('[data-testid="camera-button"]');
		await cameraButton.waitFor({ state: 'visible', timeout: 15000 });
		await cameraButton.click({ force: true });

		// Wait for capture button to be ready
		const captureButton = page.locator('[data-testid="single-capture-button"]');
		await captureButton.waitFor({ state: 'visible', timeout: 15000 });
		await expect(captureButton).toBeEnabled({ timeout: 15000 });

		// Confirm no photos yet
		const initialCount = await getPhotoCount(page);
		expect(initialCount).toBe(0);

		// Capture a photo
		await captureButton.click();
		await waitForPhotoCount(page, 1);

		// Verify photo is pending (not uploaded — we're not logged in)
		const photo = await getLatestPhoto(page);
		expect(photo).not.toBeNull();
		expect(photo!.blobSize).toBeGreaterThan(0);
		expect(photo!.status).toBe('pending');
		expect(photo!.server_photo_id).toBeNull();
		expect(photo!.latitude).toBeCloseTo(50.11692, 3);
		expect(photo!.longitude).toBeCloseTo(14.48837, 3);

		// Close camera by clicking the button again
		await cameraButton.click({ force: true });

		// Login — this triggers triggerPhotoSync() via auth subscription in captureQueue.ts
		await loginAsTestUser(page, testPasswords.test);
		await page.waitForLoadState('networkidle');

		// Debug: check photo status and console for upload activity
		const preUploadPhoto = await getLatestPhoto(page);
		console.log('After login, photo status:', JSON.stringify(preUploadPhoto));

		// Wait for auto-upload to complete (IndexedDB status changes to 'uploaded')
		await waitForUploadedCount(page, 1, 60000);

		// Verify IndexedDB photo is now uploaded with server_photo_id
		const uploadedPhoto = await getLatestPhoto(page);
		expect(uploadedPhoto).not.toBeNull();
		expect(uploadedPhoto!.status).toBe('uploaded');
		expect(uploadedPhoto!.server_photo_id).toBeTruthy();

		// Navigate to My Photos and verify photo appears on server
		await page.goto('/photos');
		await page.waitForLoadState('networkidle');

		// Click refresh if photos aren't loaded yet
		const refreshButton = page.locator('[data-testid="refresh-photos-button"]');
		if (await refreshButton.isVisible()) {
			await refreshButton.click();
		}

		// Wait for at least 1 photo in the server photos list
		const photosList = page.locator('[data-testid="photos-list"]');
		await photosList.waitFor({ state: 'visible', timeout: 15000 });

		const photoItems = photosList.locator(':scope > *');
		await expect(photoItems.first()).toBeVisible({ timeout: 10000 });
		const serverPhotoCount = await photoItems.count();
		expect(serverPhotoCount).toBeGreaterThanOrEqual(1);
	});

	test('subsequent photo after login uploads automatically', async ({ page }) => {
		// Login first
		await loginAsTestUser(page, testPasswords.test);
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Open camera
		const cameraButton = page.locator('[data-testid="camera-button"]');
		await cameraButton.waitFor({ state: 'visible', timeout: 15000 });
		await cameraButton.click({ force: true });

		const captureButton = page.locator('[data-testid="single-capture-button"]');
		await captureButton.waitFor({ state: 'visible', timeout: 15000 });
		await expect(captureButton).toBeEnabled({ timeout: 15000 });

		// Capture first photo
		await captureButton.click();
		await waitForPhotoCount(page, 1);

		// Wait for it to upload automatically (we're already logged in)
		await waitForUploadedCount(page, 1, 30000);

		const photo1 = await getLatestPhoto(page);
		expect(photo1).not.toBeNull();
		expect(photo1!.status).toBe('uploaded');
		expect(photo1!.server_photo_id).toBeTruthy();

		// Capture second photo
		await captureButton.click();
		await waitForPhotoCount(page, 2);

		// Wait for both to be uploaded
		await waitForUploadedCount(page, 2, 30000);

		const allPhotos = await getAllPhotosDetailed(page);
		const uploadedPhotos = allPhotos.filter(p => p.status === 'uploaded');
		expect(uploadedPhotos.length).toBe(2);
		expect(uploadedPhotos[0].server_photo_id).toBeTruthy();
		expect(uploadedPhotos[1].server_photo_id).toBeTruthy();

		// Close camera and verify photos on server
		await cameraButton.click({ force: true });
		await page.goto('/photos');
		await page.waitForLoadState('networkidle');

		const refreshButton = page.locator('[data-testid="refresh-photos-button"]');
		if (await refreshButton.isVisible()) {
			await refreshButton.click();
		}

		const photosList = page.locator('[data-testid="photos-list"]');
		await photosList.waitFor({ state: 'visible', timeout: 15000 });

		const photoItems = photosList.locator(':scope > *');
		await expect(photoItems.first()).toBeVisible({ timeout: 10000 });
		const serverPhotoCount = await photoItems.count();
		expect(serverPhotoCount).toBeGreaterThanOrEqual(2);
	});
});
