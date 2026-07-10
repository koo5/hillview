import { T } from './helpers/timeouts';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { enableAutoUpload } from './helpers/autoUpload';
import { seedBrowserPhoto, waitForUploadedCount, getLatestPhoto } from './helpers/indexedDbPhotos';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CAR_JPEG_BASE64 = fs
	.readFileSync(path.resolve(__dirname, '../test-assets/car.jpg'))
	.toString('base64');

// The IndexedDB-backed capture → auto-upload pipeline used to be exercised only
// on Chromium, because every test that drove it relied on the Chromium-only fake
// camera. That blind spot hid a real Firefox/WebKit bug: init() awaited
// navigator.storage.persist(), which never resolves in those engines, wedging
// the upload loop so a captured photo stayed 'pending' forever.
//
// This test drives the same pipeline WITHOUT a camera (it seeds the photo
// straight into IndexedDB), so it runs cross-browser and guards that fix.
test.describe('Auto-upload on login (web, no camera)', () => {
	test.describe.configure({ mode: 'serial' });

	test('a queued photo auto-uploads after login and appears on the server', async ({ page, testUsers, browserName }) => {
		// Playwright's WebKit (WebKitGTK) cannot persist a Blob to IndexedDB — see
		// anonymization-reupload.spec.ts for the detailed finding. The pipeline
		// stores photos as Blobs, so it is untestable on this engine. Real Safari
		// is unaffected.
		test.skip(browserName === 'webkit', 'Playwright WebKit cannot store Blobs in IndexedDB');
		test.setTimeout(180_000);

		// Seed a photo into browser storage as if captured with the camera
		await page.goto('/');
		const localPhotoId = await seedBrowserPhoto(page, CAR_JPEG_BASE64);

		// Configure auto-upload: accept license + enable
		await page.goto('/settings/upload');
		await enableAutoUpload(page);

		// Login triggers triggerPhotoSync() via the auth subscription in captureQueue.ts
		await loginAsTestUser(page, testUsers.passwords.test);

		// The auto-upload loop must run to completion — this is what the persist()
		// hang used to block. Photo transitions pending → processing/completed.
		await waitForUploadedCount(page, 1);

		const uploaded = await getLatestPhoto(page);
		expect(uploaded).not.toBeNull();
		expect(['processing', 'completed']).toContain(uploaded!.status);
		const serverPhotoId = uploaded!.server_photo_id;
		expect(serverPhotoId).toBeTruthy();

		// The same local photo carried through (not a stray)
		expect(uploaded!.id).toBe(localPhotoId);

		// Verify it actually landed on the server: it shows up in My Photos
		await page.goto('/photos');

		const refreshButton = page.locator('[data-testid="refresh-photos-button"]');
		if (await refreshButton.isVisible()) {
			await refreshButton.click();
		}

		const photosList = page.locator('[data-testid="photos-list"]');
		await photosList.waitFor({ state: 'visible', timeout: T(15000) });
		await expect(photosList.locator(`[data-photo-id="${serverPhotoId}"]`).first())
			.toBeVisible({ timeout: T(10000) });
	});
});
