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
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';
import { enableAutoUpload } from './helpers/autoUpload';
import { addCameraInitScript } from './helpers/cameraSetup';

import {
	waitForPhotoCount,
	waitForUploadedCount,
} from './helpers/indexedDbPhotos';

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

// ── Helpers ──────────────────────────────────────────────────────────

async function captureAndUploadPhoto(page: any) {
	const cameraButton = page.locator('[data-testid="camera-button"]');
	await cameraButton.waitFor({ state: 'visible', timeout: 15000 });
	await cameraButton.click({ force: true });

	const captureButton = page.locator('[data-testid="single-capture-button"]');
	await captureButton.waitFor({ state: 'visible', timeout: 15000 });
	await expect(captureButton).toBeEnabled({ timeout: 15000 });

	await captureButton.click();
	await waitForPhotoCount(page, 1);
	await waitForUploadedCount(page, 1);
}

// ── Tests ───────────────────────────────────────────────────────────

test.describe('Sync Status Reporting', () => {
	test.describe.configure({ mode: 'serial' });

	// Each test captures + uploads — need per-test isolation
	test.beforeEach(async ({ page, browserName, testUsers }) => {
		test.skip(browserName !== 'chromium', 'Fake camera only works in Chromium');
		await createTestUsers();
		await addCameraInitScript(page);

		// Login and enable auto-upload so triggerPhotoSync doesn't skip
		await loginAsTestUser(page, testUsers.passwords.test);
		await page.goto('/settings/upload');
		await page.waitForLoadState('networkidle');
		await enableAutoUpload(page);

		await page.goto('/');
		await page.waitForLoadState('networkidle');
	});

	test('fgSyncStatus reports correct phases and counts after upload', async ({ page }) => {
		// Open camera, capture, and wait for upload
		await captureAndUploadPhoto(page);

		// After upload completes, fgSyncStatus should show 'complete' phase
		const completedStatus = await getFgSyncStatus(page);
		expect(completedStatus).not.toBeNull();
		expect(completedStatus.source).toBe('fg');
		expect(completedStatus.phase).toBe('finished');
		expect(completedStatus.active).toBe(false);
		expect(completedStatus.successCount).toBeGreaterThanOrEqual(1);
		expect(completedStatus.failureCount).toBe(0);
		expect(completedStatus.totalPending).toBeGreaterThanOrEqual(1);
		expect(completedStatus.remainingCount).toBe(0);
		expect(completedStatus.timestamp).toBeGreaterThan(0);
	});

	test('fgSyncHistory records phase transitions in order', async ({ page }) => {
		await captureAndUploadPhoto(page);

		const history = await getFgSyncHistory(page);
		expect(history.length).toBeGreaterThanOrEqual(3); // starting, uploading, finished at minimum

		// First report should be 'starting'
		expect(history[0].phase).toBe('starting');
		expect(history[0].active).toBe(true);

		// Should have at least one 'uploading' phase
		const uploadingReports = history.filter((r: any) => r.phase === 'uploading');
		expect(uploadingReports.length).toBeGreaterThanOrEqual(1);

		// Last report should be 'complete'
		const lastReport = history[history.length - 1];
		expect(lastReport.phase).toBe('finished');
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

	test('combinedSyncStatus reflects foreground source after upload', async ({ page }) => {
		// Before any upload, combined should show nothing active
		const initialCombined = await getCombinedSyncStatus(page);
		expect(initialCombined).not.toBeNull();
		expect(initialCombined.isUploading).toBe(false);
		expect(initialCombined.activeSource).toBeNull();

		await captureAndUploadPhoto(page);

		// After completion, verify the final combined status
		const finalCombined = await getCombinedSyncStatus(page);
		expect(finalCombined.isUploading).toBe(false);
		// fg store should have data (phase: finished), sw should be null
		expect(finalCombined.fg).not.toBeNull();
		expect(finalCombined.fg.source).toBe('fg');
		expect(finalCombined.fg.phase).toBe('finished');
		expect(finalCombined.sw).toBeNull();
	});

	test('console logs confirm foreground upload path', async ({ page }) => {
		// Collect console messages
		const consoleMessages: string[] = [];
		page.on('console', msg => {
			consoleMessages.push(msg.text());
		});

		await captureAndUploadPhoto(page);

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
