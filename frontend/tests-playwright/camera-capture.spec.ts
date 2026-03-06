import { test, expect } from '@playwright/test';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';
import { setupConsoleLogging } from './helpers/consoleLogging';

/** Helper: get photo count from IndexedDB */
async function getPhotoCount(page: any): Promise<number> {
	return page.evaluate(() => {
		return new Promise<number>((resolve) => {
			const request = indexedDB.open('HillviewPhotoDB', 1);
			request.onerror = () => resolve(0);
			request.onsuccess = () => {
				const db = request.result;
				if (!db.objectStoreNames.contains('photos')) {
					db.close();
					resolve(0);
					return;
				}
				const tx = db.transaction('photos', 'readonly');
				const store = tx.objectStore('photos');
				const countReq = store.count();
				countReq.onsuccess = () => { db.close(); resolve(countReq.result); };
				countReq.onerror = () => { db.close(); resolve(0); };
			};
			request.onupgradeneeded = () => { request.result.close(); resolve(0); };
		});
	});
}

/** Helper: wait for IndexedDB photo count to reach target */
async function waitForPhotoCount(page: any, target: number, timeoutMs = 10000): Promise<void> {
	await page.evaluate(async ({ target, timeoutMs }: { target: number; timeoutMs: number }) => {
		const interval = 200;
		let elapsed = 0;
		while (elapsed < timeoutMs) {
			const count = await new Promise<number>((resolve) => {
				const request = indexedDB.open('HillviewPhotoDB', 1);
				request.onerror = () => resolve(0);
				request.onsuccess = () => {
					const db = request.result;
					if (!db.objectStoreNames.contains('photos')) { db.close(); resolve(0); return; }
					const tx = db.transaction('photos', 'readonly');
					const store = tx.objectStore('photos');
					const c = store.count();
					c.onsuccess = () => { db.close(); resolve(c.result); };
					c.onerror = () => { db.close(); resolve(0); };
				};
			});
			if (count >= target) return;
			await new Promise(r => setTimeout(r, interval));
			elapsed += interval;
		}
		throw new Error(`Timed out waiting for ${target} photos (waited ${timeoutMs}ms)`);
	}, { target, timeoutMs });
}

/** Helper: get the latest photo from IndexedDB */
async function getLatestPhoto(page: any): Promise<any> {
	return page.evaluate(() => {
		return new Promise<any>((resolve) => {
			const request = indexedDB.open('HillviewPhotoDB', 1);
			request.onerror = () => resolve(null);
			request.onsuccess = () => {
				const db = request.result;
				if (!db.objectStoreNames.contains('photos')) { db.close(); resolve(null); return; }
				const tx = db.transaction('photos', 'readonly');
				const store = tx.objectStore('photos');
				const allReq = store.getAll();
				allReq.onsuccess = () => {
					db.close();
					const photos = allReq.result;
					if (photos.length === 0) { resolve(null); return; }
					const newest = photos[photos.length - 1];
					resolve({
						id: newest.id,
						blobSize: newest.blob?.size ?? 0,
						latitude: newest.location?.latitude,
						longitude: newest.location?.longitude,
						uploaded: newest.uploaded,
						mode: newest.mode,
						captured_at: newest.captured_at
					});
				};
				allReq.onerror = () => { db.close(); resolve(null); };
			};
		});
	});
}

// Camera capture only works with Chromium's fake device support
test.describe('Camera Capture', () => {
	test.beforeEach(async ({ page, browserName }) => {
		test.skip(browserName !== 'chromium', 'Fake camera only works in Chromium');

		setupConsoleLogging(page);

		// Pre-seed localStorage so camera button is visible (needs debug_enabled)
		// and location data is available for capture
		await page.addInitScript(() => {
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

		// Create test users
		const result = await createTestUsers();
		await loginAsTestUser(page, result.passwords.test);
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
		expect(photo1.blobSize).toBeGreaterThan(0);
		expect(photo1.latitude).toBeCloseTo(50.11692, 3);
		expect(photo1.longitude).toBeCloseTo(14.48837, 3);
		expect(photo1.uploaded).toBe(false);

		// --- Capture photo 2 ---
		await captureButton.click();
		await waitForPhotoCount(page, 2);

		const photo2 = await getLatestPhoto(page);
		expect(photo2).not.toBeNull();
		expect(photo2.blobSize).toBeGreaterThan(0);
		expect(photo2.id).not.toBe(photo1.id);

		// --- Auto-upload prompt should appear (user not configured auto-upload) ---
		const autoUploadPrompt = page.locator('[data-testid="auto-upload-prompt"]');
		await autoUploadPrompt.waitFor({ state: 'visible', timeout: 15000 });

		// Click the green "Configure auto-upload" button
		const configureBtn = page.locator('[data-testid="configure-auto-upload"]');
		await configureBtn.click();

		// Should navigate to upload settings page
		await page.waitForURL('**/settings/upload', { timeout: 10000 });
	});
});
