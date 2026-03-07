/**
 * Tests for sync status reporting during foreground upload.
 *
 * Validates that the FG status reporter emits correct phase transitions
 * and counts when photos are captured and uploaded. Playwright's Chromium
 * doesn't support the Background Sync API, so uploads always go through
 * the foreground path — exactly what we want to test here.
 *
 * Store values are read from window.__stores, which is populated by
 * subscriptions in src/lib/syncStatus.ts.
 */

import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';

import {
	waitForPhotoCount,
	waitForUploadedCount,
} from './helpers/indexedDbPhotos';

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

// ── Helpers to read window.__stores ─────────────────────────────────

async function getFgSyncStatus(page: any): Promise<any> {
	return page.evaluate(() => (window as any).__stores?.fgSyncStatus ?? null);
}

async function getCombinedSyncStatus(page: any): Promise<any> {
	return page.evaluate(() => (window as any).__stores?.combinedSyncStatus ?? null);
}

async function getFgSyncHistory(page: any): Promise<any[]> {
	return page.evaluate(() => (window as any).__stores?.fgSyncHistory ?? []);
}

// ── Tests ───────────────────────────────────────────────────────────

test.describe('Sync Status Reporting', () => {
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ page, browserName }) => {
		test.skip(browserName !== 'chromium', 'Fake camera only works in Chromium');
		await addCameraInitScript(page);
	});

	test('fgSyncStatus reports correct phases and counts after upload', async ({ page, testUsers }) => {
		// Login first so upload triggers immediately after capture
		await loginAsTestUser(page, testUsers.passwords.test);
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Verify fgSyncStatus starts as null (no upload yet)
		const initialStatus = await getFgSyncStatus(page);
		expect(initialStatus).toBeNull();

		// Open camera and capture a photo
		const cameraButton = page.locator('[data-testid="camera-button"]');
		await cameraButton.waitFor({ state: 'visible', timeout: 15000 });
		await cameraButton.click({ force: true });

		const captureButton = page.locator('[data-testid="single-capture-button"]');
		await captureButton.waitFor({ state: 'visible', timeout: 15000 });
		await expect(captureButton).toBeEnabled({ timeout: 15000 });

		await captureButton.click();
		await waitForPhotoCount(page, 1);

		// Wait for the upload to complete (triggers triggerPhotoSync → FG path)
		await waitForUploadedCount(page, 1, 30000);

		// After upload completes, fgSyncStatus should show 'complete' phase
		const completedStatus = await getFgSyncStatus(page);
		expect(completedStatus).not.toBeNull();
		expect(completedStatus.source).toBe('fg');
		expect(completedStatus.phase).toBe('complete');
		expect(completedStatus.active).toBe(false);
		expect(completedStatus.successCount).toBeGreaterThanOrEqual(1);
		expect(completedStatus.failureCount).toBe(0);
		expect(completedStatus.totalPending).toBeGreaterThanOrEqual(1);
		expect(completedStatus.remainingCount).toBe(0);
		expect(completedStatus.timestamp).toBeGreaterThan(0);
	});

	test('fgSyncHistory records phase transitions in order', async ({ page, testUsers }) => {
		// Clean slate
		await fetch('http://localhost:8055/api/debug/recreate-test-users', { method: 'POST' });

		await loginAsTestUser(page, testUsers.passwords.test);
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Capture and upload
		const cameraButton = page.locator('[data-testid="camera-button"]');
		await cameraButton.waitFor({ state: 'visible', timeout: 15000 });
		await cameraButton.click({ force: true });

		const captureButton = page.locator('[data-testid="single-capture-button"]');
		await captureButton.waitFor({ state: 'visible', timeout: 15000 });
		await expect(captureButton).toBeEnabled({ timeout: 15000 });

		await captureButton.click();
		await waitForPhotoCount(page, 1);
		await waitForUploadedCount(page, 1, 30000);

		const history = await getFgSyncHistory(page);
		expect(history.length).toBeGreaterThanOrEqual(3); // starting, uploading, complete at minimum

		// First report should be 'starting'
		expect(history[0].phase).toBe('starting');
		expect(history[0].active).toBe(true);

		// Should have at least one 'uploading' phase
		const uploadingReports = history.filter((r: any) => r.phase === 'uploading');
		expect(uploadingReports.length).toBeGreaterThanOrEqual(1);

		// Last report should be 'complete'
		const lastReport = history[history.length - 1];
		expect(lastReport.phase).toBe('complete');
		expect(lastReport.active).toBe(false);

		// Timestamps should be monotonically non-decreasing
		for (let i = 1; i < history.length; i++) {
			expect(history[i].timestamp).toBeGreaterThanOrEqual(history[i - 1].timestamp);
		}

		// All reports should have source 'fg'
		for (const report of history) {
			expect(report.source).toBe('fg');
		}
	});

	test('combinedSyncStatus reflects foreground source after upload', async ({ page, testUsers }) => {
		// Clean slate
		await fetch('http://localhost:8055/api/debug/recreate-test-users', { method: 'POST' });

		await loginAsTestUser(page, testUsers.passwords.test);
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Before any upload, combined should show nothing active
		const initialCombined = await getCombinedSyncStatus(page);
		expect(initialCombined).not.toBeNull();
		expect(initialCombined.isUploading).toBe(false);
		expect(initialCombined.activeSource).toBeNull();

		// Capture a photo
		const cameraButton = page.locator('[data-testid="camera-button"]');
		await cameraButton.waitFor({ state: 'visible', timeout: 15000 });
		await cameraButton.click({ force: true });

		const captureButton = page.locator('[data-testid="single-capture-button"]');
		await captureButton.waitFor({ state: 'visible', timeout: 15000 });
		await expect(captureButton).toBeEnabled({ timeout: 15000 });

		await captureButton.click();
		await waitForPhotoCount(page, 1);
		await waitForUploadedCount(page, 1, 30000);

		// After completion, verify the final combined status
		const finalCombined = await getCombinedSyncStatus(page);
		expect(finalCombined.isUploading).toBe(false);
		// fg store should have data (phase: complete), sw should be null
		expect(finalCombined.fg).not.toBeNull();
		expect(finalCombined.fg.source).toBe('fg');
		expect(finalCombined.fg.phase).toBe('complete');
		expect(finalCombined.sw).toBeNull();
	});

	test('console logs confirm foreground upload path', async ({ page, testUsers }) => {
		// Clean slate
		await fetch('http://localhost:8055/api/debug/recreate-test-users', { method: 'POST' });

		// Collect console messages
		const consoleMessages: string[] = [];
		page.on('console', msg => {
			consoleMessages.push(msg.text());
		});

		await loginAsTestUser(page, testUsers.passwords.test);
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Capture a photo
		const cameraButton = page.locator('[data-testid="camera-button"]');
		await cameraButton.waitFor({ state: 'visible', timeout: 15000 });
		await cameraButton.click({ force: true });

		const captureButton = page.locator('[data-testid="single-capture-button"]');
		await captureButton.waitFor({ state: 'visible', timeout: 15000 });
		await expect(captureButton).toBeEnabled({ timeout: 15000 });

		await captureButton.click();
		await waitForPhotoCount(page, 1);
		await waitForUploadedCount(page, 1, 30000);

		// Verify FG path was taken
		const fgLogFound = consoleMessages.some(msg =>
			msg.includes('Using foreground upload')
		);
		expect(fgLogFound, 'Expected "Using foreground upload" console message').toBe(true);

		// Verify successful upload log
		const successLogFound = consoleMessages.some(msg =>
			msg.includes('Successfully uploaded')
		);
		expect(successLogFound, 'Expected "Successfully uploaded" console message').toBe(true);
	});
});
