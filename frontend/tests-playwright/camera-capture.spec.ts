import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { getPhotoCount, waitForPhotoCount, getLatestPhoto } from './helpers/indexedDbPhotos';
import { configureAutoUploadFromPrompt } from './helpers/autoUpload';
import { addCameraInitScript } from './helpers/cameraSetup';

// Camera capture only works with Chromium's fake device support
test.describe('Camera Capture', () => {
	test.beforeEach(async ({ page, browserName, testUsers }) => {
		test.skip(browserName !== 'chromium', 'Fake camera only works in Chromium');

		await addCameraInitScript(page);

		await loginAsTestUser(page, testUsers.passwords.test);
		await page.waitForLoadState('networkidle');
	});

	test('should capture two photos, save to IndexedDB, and show auto-upload prompt', async ({ page }) => {
		// Wait for the camera button to appear (requires debug_enabled or TAURI)
		const cameraButton = page.locator('[data-testid="camera-button"]');
		await cameraButton.waitFor({ state: 'visible', timeout: 15000 });

		// Open camera (force: true because the button has a rotating CSS transform
		// from device orientation that makes Playwright see it as "not stable")
		await cameraButton.click({ force: true });

		// Wait for the capture button to become enabled (implies cameraReady && locationData)
		const captureButton = page.locator('[data-testid="single-capture-button"]');
		await captureButton.waitFor({ state: 'visible', timeout: 15000 });
		await expect(captureButton).toBeEnabled({ timeout: 15000 });

		// Verify video has non-zero dimensions (fake device or synthetic fallback)
		const videoDimensions = await page.evaluate(() => {
			const video = document.querySelector('video.camera-video') as HTMLVideoElement;
			return video ? { width: video.videoWidth, height: video.videoHeight } : null;
		});
		expect(videoDimensions).not.toBeNull();
		expect(videoDimensions!.width).toBeGreaterThan(0);
		expect(videoDimensions!.height).toBeGreaterThan(0);

		// Confirm no photos yet
		const initialCount = await getPhotoCount(page);
		expect(initialCount).toBe(0);

		// --- Capture photo 1 ---
		await captureButton.click();
		await waitForPhotoCount(page, 1);

		const photo1 = await getLatestPhoto(page);
		expect(photo1).not.toBeNull();
		expect(photo1!.blobSize).toBeGreaterThan(0);
		expect(photo1!.latitude).toBeCloseTo(50.11692, 3);
		expect(photo1!.longitude).toBeCloseTo(14.48837, 3);
		// Photo should be pending (or uploading/processing/completed if auto-upload is fast)
		expect(['pending', 'uploading', 'processing', 'completed']).toContain(photo1!.status);

		// --- Capture photo 2 ---
		await captureButton.click();
		await waitForPhotoCount(page, 2);

		const photo2 = await getLatestPhoto(page);
		expect(photo2).not.toBeNull();
		expect(photo2!.blobSize).toBeGreaterThan(0);
		expect(photo2!.id).not.toBe(photo1!.id);

		// --- Auto-upload prompt should appear (user not configured auto-upload) ---
		// Walk through: prompt → settings/upload → license → enable
		await configureAutoUploadFromPrompt(page);
	});
});
