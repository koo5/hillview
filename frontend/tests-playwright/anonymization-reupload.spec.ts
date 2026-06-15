import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { enableAutoUpload } from './helpers/autoUpload';
import {
	seedBrowserPhoto,
	getPhotoReuploadState,
	waitForReuploadedVersion,
	waitForUploadedCount,
	getLatestPhoto
} from './helpers/indexedDbPhotos';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Real photo of a vehicle — exercises the same content the worker's
// anonymization (license plate / face blur) acts on.
const CAR_JPEG_BASE64 = fs
	.readFileSync(path.resolve(__dirname, '../test-assets/car.jpg'))
	.toString('base64');

test.describe('Anonymization re-upload (web)', () => {
	test.describe.configure({ mode: 'serial' });

	test('changing anonymization to none re-uploads the photo with a bumped version', async ({ page, testUsers, browserName }) => {
		// Playwright's WebKit (WebKitGTK) cannot persist a Blob to IndexedDB —
		// every Blob put fails with "Error preparing Blob/File data to be stored
		// in object store" (verified across Blob/ArrayBuffer/fetched-Blob; raw
		// Uint8Array works). The whole browser-capture pipeline stores photos as
		// Blobs, so it is untestable on this engine. Real Safari is unaffected.
		test.skip(browserName === 'webkit', 'Playwright WebKit cannot store Blobs in IndexedDB');
		test.setTimeout(180_000);

		// Seed a photo into browser storage as if captured with the camera
		await page.goto('/');
		const localPhotoId = await seedBrowserPhoto(page, CAR_JPEG_BASE64);

		// Configure auto-upload: license + enable
		await page.goto('/settings/upload');
		await enableAutoUpload(page);

		// Login triggers photo sync (auth subscription in captureQueue.ts)
		await loginAsTestUser(page, testUsers.passwords.test);
		await page.waitForLoadState('networkidle');

		// Initial upload completes at implicit version 1
		await waitForUploadedCount(page, 1);
		const uploaded = await getLatestPhoto(page);
		expect(uploaded).not.toBeNull();
		const serverPhotoId = uploaded!.server_photo_id!;
		expect(serverPhotoId).toBeTruthy();

		// Open My Photos and find our photo's menu
		await page.goto('/photos');
		await page.waitForLoadState('networkidle');

		const refreshButton = page.locator('[data-testid="refresh-photos-button"]');
		if (await refreshButton.isVisible()) {
			await refreshButton.click();
		}

		const photosList = page.locator('[data-testid="photos-list"]');
		await photosList.waitFor({ state: 'visible', timeout: 11 * 15000 });
		await expect(photosList.locator(`[data-photo-id="${serverPhotoId}"]`).first())
			.toBeVisible({ timeout: 11 * 10000 });

		// Only one photo on the server (users recreated per spec file),
		// so there is exactly one menu button
		const menuButton = page.locator('[data-testid="photo-menu-button"]');
		// Strict locator: also guards against the dropdown rendering twice
		// (DropdownMenu must only be mounted once, in +layout.svelte)
		const anonymizationMenuItem = page.locator('[data-testid="menu-anonymization-options"]');
		await menuButton.click();
		await anonymizationMenuItem.click();

		// The modal must offer the options in the browser — this guards the
		// regression where it showed "Not available in browser yet"
		const modal = page.locator('[data-testid="anonymization-modal"]');
		await modal.waitFor({ state: 'visible', timeout: 11 * 10000 });

		const autoOption = page.locator('[data-testid="option-auto-anonymize"]');
		const skipOption = page.locator('[data-testid="option-skip-anonymization"]');
		await skipOption.waitFor({ state: 'visible', timeout: 11 * 15000 });
		await expect(autoOption).toHaveClass(/selected/);

		// Choose "No anonymization" — queues the photo for re-upload
		await skipOption.click();
		await expect(
			page.locator('[data-testid^="alert-area-"]').filter({ hasText: 'queued for re-upload' })
		).toBeVisible({ timeout: 11 * 5000 });

		// The photo re-uploads with version 2 and the override attached,
		// replacing the same server photo
		const reuploaded = await waitForReuploadedVersion(page, localPhotoId, 2);
		expect(reuploaded.version).toBe(2);
		expect(reuploaded.anonymization_override).toBe('[]');
		expect(reuploaded.server_photo_id).toBe(serverPhotoId);

		// Reopen the modal — "No anonymization" is now the current state
		await menuButton.click();
		await anonymizationMenuItem.click();
		await skipOption.waitFor({ state: 'visible', timeout: 11 * 15000 });
		await expect(skipOption).toHaveClass(/selected/, { timeout: 11 * 10000 });

		// Switching back to auto-detect queues another re-upload (version 3)
		await autoOption.click();
		const reverted = await waitForReuploadedVersion(page, localPhotoId, 3);
		expect(reverted.version).toBe(3);
		expect(reverted.anonymization_override).toBeNull();
		expect(reverted.server_photo_id).toBe(serverPhotoId);
	});
});
