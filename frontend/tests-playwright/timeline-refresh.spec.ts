import { test, expect } from './fixtures';
import { loginAs, logoutUser } from './helpers/testUsers';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { getPhotoCount, waitForPhotoCount } from './helpers/indexedDbPhotos';

/**
 * Timeline panel: refresh button (cross-user re-anchor) + cursor-follow.
 *
 * Seeds two users' photos at distinct map positions by *capturing* through the
 * fake camera (chromium-only). Capture is the right seeding tool here: the
 * fixture stamps unique pixels into every frame so server MD5 de-dup never
 * fires, and a canvas frame carries no EXIF GPS, so the map-center location we
 * set is authoritative. The photo lands at spatialState.center, which we point
 * per-capture via localStorage so each photo gets its own clickable marker.
 */

// Distinct positions (~140m apart) so each photo is an individually clickable
// marker. A1/A2 belong to user `test` (the walk anchor + an in-window sibling);
// B1 belongs to `testuser` (a different owner → always out of test's window).
const CENTER = { lat: 50.1156, lng: 14.494 };
const A1 = { lat: 50.115, lng: 14.4932 };
const A2 = { lat: 50.1152, lng: 14.4952 };
const B1 = { lat: 50.1163, lng: 14.4943 };
const COORD_EPS = 6e-4; // ~50m; well inside the ~140m point spacing

// Server photo ids, resolved during setup and reused by the behavior tests.
let idA1 = '';
let idA2 = '';
let idB1 = '';

/** Enable the camera button (debug) + a bearing; center is set per-capture. */
function addCaptureInit(page: any) {
	return page.addInitScript(() => {
		const a = JSON.parse(localStorage.getItem('appSettings') || '{}');
		a.debug_enabled = true;
		a.activity = 'view';
		localStorage.setItem('appSettings', JSON.stringify(a));
		localStorage.setItem('bearingState', JSON.stringify({ bearing: 141, source: 'map', accuracy_level: null }));
	});
}

/** Read every IndexedDB photo's server id + capture location. */
function dumpPhotos(page: any): Promise<Array<{ server: string | null; status: string; lat?: number; lng?: number }>> {
	return page.evaluate(() => new Promise<any[]>((resolve) => {
		const req = indexedDB.open('HillviewPhotoDB');
		req.onerror = () => resolve([]);
		req.onsuccess = () => {
			const db = req.result;
			if (!db.objectStoreNames.contains('photos')) { db.close(); resolve([]); return; }
			const all = db.transaction('photos', 'readonly').objectStore('photos').getAll();
			all.onsuccess = () => {
				db.close();
				resolve(all.result.map((p: any) => ({
					server: p.server_photo_id || null,
					status: p.status,
					lat: p.metadata?.location?.latitude,
					lng: p.metadata?.location?.longitude,
				})));
			};
			all.onerror = () => { db.close(); resolve([]); };
		};
		req.onupgradeneeded = () => { (req as IDBOpenDBRequest).result.close(); resolve([]); };
	}));
}

/**
 * Enable the license + auto-upload, but only toggle when actually off. The setting
 * is client-side and persists across logout in the same context, so for the second
 * user the radio is already on — and re-checking it fires no save (so the "saved"
 * confirmation never appears). Idempotent here: wait for the alert only when we change it.
 */
async function ensureAutoUpload(page: any) {
	await page.goto('/settings/upload');
	const license = page.locator('[data-testid="license-checkbox"]');
	await license.waitFor({ state: 'visible', timeout: 11 * 10000 });
	if (!(await license.isChecked())) await license.check();
	const enabled = page.locator('[data-testid="auto-upload-enabled"]');
	if (!(await enabled.isChecked())) {
		await enabled.check();
		await page.locator('[data-testid="alert-message"]').waitFor({ state: 'visible', timeout: 11 * 5000 });
	}
}

/** Capture one photo at (lat, lon) via the fake camera. */
async function captureAt(page: any, lat: number, lon: number) {
	// Point the map (= the captured photo's location) at the target, then load.
	await page.evaluate(({ lat, lon }: { lat: number; lon: number }) => {
		localStorage.setItem('spatialState', JSON.stringify({ center: { lat, lng: lon }, zoom: 20, bounds: null, range: 1000, source: 'map' }));
	}, { lat, lon });
	await page.goto('/');

	const cameraButton = page.locator('[data-testid="camera-button"]');
	await cameraButton.waitFor({ state: 'visible', timeout: 11 * 15000 });
	await cameraButton.click({ force: true });

	const captureButton = page.locator('[data-testid="single-capture-button"]');
	await captureButton.waitFor({ state: 'visible', timeout: 11 * 15000 });
	await expect(captureButton).toBeEnabled({ timeout: 11 * 15000 });

	const before = await getPhotoCount(page);
	await captureButton.click();
	await waitForPhotoCount(page, before + 1, 20000);
}

/** Poll until the photo captured at `target` has uploaded; return its server id. */
async function waitUploadedAtCoord(page: any, target: { lat: number; lng: number }, timeoutMs = 130000): Promise<string> {
	const interval = 1500;
	let elapsed = 0;
	while (elapsed < timeoutMs) {
		const match = (await dumpPhotos(page)).find(p =>
			p.server && (p.status === 'processing' || p.status === 'completed') &&
			typeof p.lat === 'number' && typeof p.lng === 'number' &&
			Math.abs(p.lat - target.lat) < COORD_EPS && Math.abs(p.lng! - target.lng) < COORD_EPS);
		if (match) return match.server!;
		await new Promise(r => setTimeout(r, interval));
		elapsed += interval;
	}
	throw new Error(`Timed out waiting for upload at ${JSON.stringify(target)}. Photos: ${JSON.stringify(await dumpPhotos(page))}`);
}

/** Load the cluster, enable Hillview, and wait for all three seeded markers. */
async function openClusterMap(page: any) {
	await page.goto(`/?lat=${CENTER.lat}&lon=${CENTER.lng}&zoom=18`);
	await ensureSourceEnabled(page, 'hillview', true);
	// A freshly uploaded photo doesn't appear on an already-loaded area until the
	// source is re-streamed (pan / source toggle / reload). Re-toggle the source
	// until all three markers render — this also rides out the last upload finishing
	// processing, and keeps hunter mode on (a reload would reset it), which we need to
	// click-select the non-featured captured photos.
	const toggle = page.locator('[data-testid="source-toggle-hillview"]');
	for (let attempt = 0; attempt < 12; attempt++) {
		const have = await page.evaluate(
			(ids: string[]) => ids.filter(id => document.querySelector(`.marker-container[data-photo-id="${id}"]`)).length,
			[idA1, idA2, idB1],
		);
		if (have === 3) return;
		await toggle.click();
		await page.waitForTimeout(800); // source off
		await toggle.click();
		await page.waitForTimeout(2500); // source on → re-stream the area
	}
	throw new Error('Seeded markers did not all appear after re-streaming the source');
}

/**
 * Select a photo by its marker. These markers are doubly awkward to click: the
 * container is `transform: translate()`-offset from its paint box (so a `{ force }`
 * click fires at the bbox centre — dead space — and misses), and they re-render/detach
 * continuously while the timeline is open (so a plain `.click()` never passes Playwright's
 * stability gate). `dispatchEvent` handles both: it only needs the element attached and
 * fires the event straight at it — exactly what the map's delegated handler consumes
 * (`target.closest('.marker-container[data-photo-id]')`).
 */
async function clickMarker(page: any, id: string) {
	const marker = page.locator(`.marker-container[data-photo-id="${id}"]`);
	await marker.waitFor({ state: 'attached', timeout: 11 * 15000 });
	await marker.dispatchEvent('click');
	// Confirm the photo became the selected/front one before continuing (the marker
	// re-renders with `.bearing-circle.selected` when it's photoInFront).
	await page.waitForFunction(
		(pid: string) => !!document.querySelector(`.marker-container[data-photo-id="${pid}"] .bearing-circle.selected`),
		id,
		{ timeout: 11 * 10000 },
	);
}

test.describe('Timeline refresh + cursor-follow', () => {
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ browserName }) => {
		// Capture pipeline needs the fake camera (Chromium flags) and stores photo
		// Blobs in IndexedDB (WebKitGTK can't); both make this Chromium-only.
		test.skip(browserName !== 'chromium', 'Capture/fake-camera is Chromium-only');
	});

	test('setup: capture photos for two users at distinct positions', async ({ page, testUsers }) => {
		test.setTimeout(300_000);
		await addCaptureInit(page);

		// User A (`test`): two photos → the walk anchor + an in-window sibling.
		await loginAs(page, 'test', testUsers.passwords.test);
		await ensureAutoUpload(page);
		await captureAt(page, A1.lat, A1.lng);
		await captureAt(page, A2.lat, A2.lng);
		idA1 = await waitUploadedAtCoord(page, A1);
		idA2 = await waitUploadedAtCoord(page, A2);

		// User B (`testuser`): one photo at a separate spot → an out-of-window pick.
		await logoutUser(page);
		await loginAs(page, 'testuser', testUsers.passwords.testuser);
		await ensureAutoUpload(page);
		await captureAt(page, B1.lat, B1.lng);
		idB1 = await waitUploadedAtCoord(page, B1);

		expect(new Set([idA1, idA2, idB1]).size).toBe(3);
	});

	test('selecting an in-window photo moves the cursor (no refresh button)', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAs(page, 'test', testUsers.passwords.test);
		await openClusterMap(page);

		// Anchor the walk on A1 (oldest of test's two photos → row 1 / 2).
		await clickMarker(page, idA1);
		await page.keyboard.press('t');
		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });
		const status = page.getByTestId('timeline-status');
		await expect(status).toHaveText('1 / 2', { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0);

		// Select the other in-window photo on the map → the cursor follows to it.
		await clickMarker(page, idA2);
		await expect(status).toHaveText('2 / 2', { timeout: 11 * 15000 });
		// Still in-window → no refresh button.
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0);
	});

	test('selecting another user\'s photo shows refresh; clicking it switches the walk', async ({ page, testUsers }) => {
		test.setTimeout(180_000);
		await loginAs(page, 'test', testUsers.passwords.test);
		await openClusterMap(page);

		// Anchor on test's photo; the walk tracks only `test`.
		await clickMarker(page, idA1);
		await page.keyboard.press('t');
		const panel = page.getByTestId('timeline-panel');
		await expect(panel).toBeVisible({ timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-status')).toHaveText('1 / 2', { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-user')).toHaveText('test');
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0);

		// Select testuser's photo — outside test's window → refresh button appears,
		// and the cursor does NOT move (it isn't in the loaded walk).
		await clickMarker(page, idB1);
		await expect(page.getByTestId('timeline-refresh')).toBeVisible({ timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-status')).toHaveText('1 / 2');

		// Refresh re-anchors on the new owner (drop-merge branch): walk switches to
		// testuser, the button clears, and the picked photo is now the in-window anchor.
		await page.getByTestId('timeline-refresh').click();
		await expect(page.getByTestId('timeline-refresh')).toHaveCount(0, { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-user')).toHaveText('testuser', { timeout: 11 * 15000 });
		await expect(page.getByTestId('timeline-status')).toHaveText('1 / 1', { timeout: 11 * 15000 });
	});
});
