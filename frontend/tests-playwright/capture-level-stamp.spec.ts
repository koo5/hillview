/**
 * The web capture's gravity stamp and level indicator (docs/todo/web-capture-level-stamp.md).
 *
 * Chromium only: the fake camera, and the CDP overrides that stand in for the
 * phone's sensors. Emulation.setSensorOverrideReadings feeds GravitySensor, the
 * source on Chromium; DeviceOrientation.setDeviceOrientationOverride feeds the
 * deviceorientation fallback that iOS Safari and Firefox use.
 *
 * Chromium delivers a sensor event only when the reading changes, and a real
 * handheld sensor always does. A constant override would deliver one reading
 * and then go stale, so the helpers below keep re-sending it with a jitter far
 * below anything the indicator rounds to.
 *
 * The vectors come from backend/common/capture_pose_cases.json.
 */
import type { CDPSession, Page } from '@playwright/test';
import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAsTestUser } from './helpers/testUsers';
import { addCameraInitScript } from './helpers/cameraSetup';
import { configureAutoUploadFromPrompt } from './helpers/autoUpload';
import { waitForPhotoCount, waitForUploadedCount, getLatestPhoto } from './helpers/indexedDbPhotos';
import { psql } from './helpers/psql';

type Vec3 = [number, number, number];

const PORTRAIT_DOWN_5_CCW_4: Vec3 = [0.68147, 9.745536, 0.854699]; // pitch -5, roll -4: level
const DOWN_25_ROLLED_12: Vec3 = [-1.847887, 8.693623, 4.144469]; // pitch -25, roll 12: tilted
const FLAT_FACE_UP: Vec3 = [0, 0, 9.80665]; // flat, looking at the ground

/** Keep a sensor override streaming until stop(); set() changes what it says. */
function stream(send: (jitter: number) => Promise<unknown>) {
	let n = 0;
	let stopped = false;
	let pending: Promise<unknown> = Promise.resolve();
	const timer = setInterval(() => {
		if (stopped) return;
		pending = send(n++ % 2 ? 1e-4 : -1e-4).catch(() => {});
	}, 40);
	return async () => {
		stopped = true;
		clearInterval(timer);
		await pending;
	};
}

async function streamGravity(cdp: CDPSession, holder: { g: Vec3 }) {
	await cdp.send('Emulation.setSensorOverrideEnabled', { enabled: true, type: 'gravity' });
	return stream((j) => cdp.send('Emulation.setSensorOverrideReadings', {
		type: 'gravity',
		reading: { xyz: { x: holder.g[0] + j, y: holder.g[1] + j, z: holder.g[2] } }
	}));
}

async function streamOrientation(cdp: CDPSession, holder: { beta: number; gamma: number }) {
	// No gravity sensor on this "device": GravitySensor fails and the app falls back.
	await cdp.send('Emulation.setSensorOverrideEnabled', {
		enabled: true, type: 'gravity', metadata: { available: false }
	});
	// A coarser jitter (0.15°), in case deviceorientation filters out tiny changes.
	return stream((j) => cdp.send('DeviceOrientation.setDeviceOrientationOverride', {
		alpha: 0, beta: holder.beta + j * 1500, gamma: holder.gamma
	}));
}

async function openCamera(page: Page) {
	const cameraButton = page.locator('[data-testid="camera-button"]');
	await cameraButton.waitFor({ state: 'visible', timeout: T(15000) });
	await cameraButton.click({ force: true });
	const captureButton = page.locator('[data-testid="single-capture-button"]');
	await captureButton.waitFor({ state: 'visible', timeout: T(15000) });
	await expect(captureButton).toBeEnabled({ timeout: T(15000) });
	return captureButton;
}

/** The stored capture's `inertial` stamp, straight from IndexedDB. */
async function latestInertial(page: Page): Promise<any> {
	return page.evaluate(() => new Promise((resolve) => {
		const request = indexedDB.open('HillviewPhotoDB');
		request.onsuccess = () => {
			const db = request.result;
			const all = db.transaction('photos', 'readonly').objectStore('photos').getAll();
			all.onsuccess = () => {
				db.close();
				const photos = all.result;
				resolve(photos.length ? photos[photos.length - 1].metadata?.inertial ?? null : undefined);
			};
		};
	}));
}

const indicator = (page: Page) => page.locator('[data-testid="capture-level-indicator"]');

test.describe('Capture level stamp', () => {
	test.beforeEach(async ({ page, browserName, context }) => {
		test.skip(browserName !== 'chromium', 'Fake camera and sensor overrides are Chromium-only');
		await context.grantPermissions(['camera', 'accelerometer', 'gyroscope']);
		await addCameraInitScript(page);
	});

	test('the indicator follows the gravity sensor', async ({ page }) => {
		await page.goto('/');
		const cdp = await page.context().newCDPSession(page);
		const holder = { g: PORTRAIT_DOWN_5_CCW_4 };
		const stop = await streamGravity(cdp, holder);
		try {
			await openCamera(page);
			await expect(indicator(page)).toHaveAttribute('data-level-state', 'level', { timeout: T(10000) });
			await expect(indicator(page)).toHaveAttribute('data-level-source', 'gravity-sensor');
			await expect(page.getByTestId('capture-level-words')).toHaveText('✓ Level');

			holder.g = DOWN_25_ROLLED_12;
			await expect(indicator(page)).toHaveAttribute('data-level-state', 'tilted');
			await expect(page.getByTestId('capture-level-words')).toHaveText('Tilted down 25° · Horizon tilted 12°');

			holder.g = FLAT_FACE_UP;
			await expect(indicator(page)).toHaveAttribute('data-level-state', 'flat');
			await expect(page.getByTestId('capture-level-words')).toHaveText('Pointing at the ground');
		} finally {
			await stop();
		}
	});

	test('the indicator falls back to deviceorientation', async ({ page }) => {
		await page.goto('/');
		const cdp = await page.context().newCDPSession(page);
		// 'portrait-down-8-ccw-25' and 'upright-looking-down-5' in the fixture
		const holder = { beta: 63.8298, gamma: -71.6056 };
		const stop = await streamOrientation(cdp, holder);
		try {
			await openCamera(page);
			await expect(indicator(page)).toHaveAttribute('data-level-state', 'tilted', { timeout: T(10000) });
			await expect(indicator(page)).toHaveAttribute('data-level-source', 'deviceorientation');
			await expect(page.getByTestId('capture-level-words')).toHaveText('Horizon tilted 25°');

			holder.beta = 85;
			holder.gamma = 0;
			await expect(indicator(page)).toHaveAttribute('data-level-state', 'level');
		} finally {
			await stop();
		}
	});

	for (const sharing of [true, false]) {
		test(`without a sensor it says so, naming Panoramax only while sharing is ${sharing ? 'on' : 'off'}`, async ({ page }) => {
			await page.addInitScript((on) => localStorage.setItem('capturePanoramaxShare', JSON.stringify(on)), sharing);
			await page.goto('/');
			const cdp = await page.context().newCDPSession(page);
			await cdp.send('Emulation.setSensorOverrideEnabled', {
				enabled: true, type: 'gravity', metadata: { available: false }
			});
			const captureButton = await openCamera(page);
			await expect(indicator(page)).toHaveAttribute('data-level-state', 'unmeasured');
			const note = page.getByTestId('capture-level-unmeasured-note');
			await expect(note).toContainText('Tilt not measured.');
			if (sharing) await expect(note).toContainText('cannot be published to Panoramax');
			else await expect(note).not.toContainText('Panoramax');
			await expect(page.getByTestId('capture-level-words')).toHaveCount(0);
			// The shutter is never refused, and the capture is simply unmeasured.
			await captureButton.click();
			await waitForPhotoCount(page, 1);
			expect(await latestInertial(page)).toBeNull();
		});
	}

	test('car mode hides the indicator', async ({ page }) => {
		await page.addInitScript(() => localStorage.setItem('bearingMode', '"car"'));
		await page.goto('/');
		const cdp = await page.context().newCDPSession(page);
		const stop = await streamGravity(cdp, { g: DOWN_25_ROLLED_12 });
		try {
			await openCamera(page);
			await expect(page.getByTestId('capture-level-indicator')).toHaveCount(0);
		} finally {
			await stop();
		}
	});

	test('a capture carries the stamp, and its server row the pitch and roll', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAsTestUser(page, testUsers.passwords.test);
		await page.goto('/');
		const cdp = await page.context().newCDPSession(page);
		const stop = await streamGravity(cdp, { g: PORTRAIT_DOWN_5_CCW_4 });
		let photoId: string | null = null;
		try {
			const captureButton = await openCamera(page);
			await expect(indicator(page)).toHaveAttribute('data-level-state', 'level', { timeout: T(10000) });
			await captureButton.click();
			await waitForPhotoCount(page, 1);

			const inertial = await latestInertial(page);
			expect(inertial).toMatchObject({ gravity_source: 'gravity-sensor', window_ms: 300 });
			expect(inertial.sample_count).toBeGreaterThan(1);
			expect(inertial.age_ms).toBeLessThan(300);
			// Chromium rounds each axis of a motion sensor reading to 0.1 m/s² (a
			// fingerprinting mitigation), so the stamp is the override's rounded value.
			inertial.gravity.forEach((v: number, i: number) =>
				expect(Math.abs(v - PORTRAIT_DOWN_5_CCW_4[i])).toBeLessThan(0.1));

			await configureAutoUploadFromPrompt(page);
			await waitForUploadedCount(page, 1);
			photoId = (await getLatestPhoto(page))!.server_photo_id;
			expect(photoId).toBeTruthy();
		} finally {
			await stop();
		}

		// pitch and roll are columns the API does not serve; read the row.
		await expect.poll(
			() => psql(`SELECT processing_status FROM photos WHERE id = '${photoId}';`),
			{ timeout: T(60000), intervals: [1000] }
		).toBe('completed');
		const [pitch, roll] = psql(`SELECT pitch, roll FROM photos WHERE id = '${photoId}';`).split('|').map(Number);
		expect(pitch).toBeCloseTo(-5, 0);
		expect(roll).toBeCloseTo(-4, 0);
		const comment = JSON.parse(psql(`SELECT exif_data->'data'->>'UserComment' FROM photos WHERE id = '${photoId}';`));
		expect(comment.inertial.gravity_source).toBe('gravity-sensor');
		expect(comment.attitude).toBeUndefined();
		expect(comment.capture_timing).toBeUndefined();
	});
});
