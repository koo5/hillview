/**
 * Shared seeding helpers for the timeline specs.
 *
 * Photos are seeded by *capturing* through the fake camera (chromium-only): the fixture
 * stamps unique pixels into every frame so server MD5 de-dup never fires, and a canvas
 * frame carries no EXIF GPS/bearing, so the map-centre location and compass bearing we set
 * per capture are authoritative. Each photo lands at spatialState.center with bearingState
 * .bearing, both pointed via localStorage before the capture page loads.
 */
import { expect } from '../fixtures';
import { ensureSourceEnabled } from './sourceHelpers';
import { getPhotoCount, waitForPhotoCount } from './indexedDbPhotos';

export const COORD_EPS = 6e-4; // ~50m; comfortably inside the spacing we seed at

/** Enable the camera button (debug). Center/bearing are set per-capture, not here. */
export function addCaptureInit(page: any) {
	return page.addInitScript(() => {
		const a = JSON.parse(localStorage.getItem('appSettings') || '{}');
		a.debug_enabled = true;
		a.activity = 'view';
		localStorage.setItem('appSettings', JSON.stringify(a));
	});
}

/** Read every IndexedDB photo's server id + capture location. */
export function dumpPhotos(page: any): Promise<Array<{ server: string | null; status: string; lat?: number; lng?: number }>> {
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
 * Enable the license + auto-upload, but only toggle when actually off. The setting is
 * client-side and persists across logout in the same context, so for a second/third user
 * the radio is already on — and re-checking it fires no save (the "saved" confirmation
 * never appears). Idempotent: wait for the alert only when we change it.
 */
export async function ensureAutoUpload(page: any) {
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

/** Capture one photo at (lat, lon) facing `bearing` via the fake camera. */
export async function captureAt(page: any, lat: number, lon: number, bearing = 141) {
	// Point the map (= the captured photo's location) and compass at the target, then load.
	await page.evaluate(({ lat, lon, bearing }: { lat: number; lon: number; bearing: number }) => {
		localStorage.setItem('spatialState', JSON.stringify({ center: { lat, lng: lon }, zoom: 20, bounds: null, range: 1000, source: 'map' }));
		localStorage.setItem('bearingState', JSON.stringify({ bearing, source: 'map', accuracy_level: null }));
	}, { lat, lon, bearing });
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
export async function waitUploadedAtCoord(page: any, target: { lat: number; lng: number }, timeoutMs = 130000): Promise<string> {
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

/** Poll until an uploaded photo whose server id isn't in `exclude` appears; return its id.
 *  Use for co-located photos that a coordinate match can't tell apart. */
export async function waitNewUpload(page: any, exclude: Set<string>, timeoutMs = 130000): Promise<string> {
	const interval = 1500;
	let elapsed = 0;
	while (elapsed < timeoutMs) {
		const m = (await dumpPhotos(page)).find(p =>
			p.server && (p.status === 'processing' || p.status === 'completed') && !exclude.has(p.server));
		if (m) return m.server!;
		await new Promise(r => setTimeout(r, interval));
		elapsed += interval;
	}
	throw new Error(`Timed out waiting for a new upload (excluding ${[...exclude].join(',') || 'none'})`);
}

/**
 * Centre the map on `center`, enable Hillview, and wait for the given markers. A freshly
 * uploaded photo doesn't appear on an already-loaded area until the source is re-streamed
 * (pan / source toggle / reload), so re-toggle until the markers render — this also rides
 * out the last upload finishing processing, and keeps hunter mode on (a reload would reset
 * it), which we need to click-select the non-featured captured photos.
 */
export async function openMap(page: any, center: { lat: number; lng: number }, requiredIds: string[], bearing?: number) {
	const b = bearing === undefined ? '' : `&bearing=${bearing}`;
	await page.goto(`/?lat=${center.lat}&lon=${center.lng}&zoom=18${b}`);
	await ensureSourceEnabled(page, 'hillview', true);
	const toggle = page.locator('[data-testid="source-toggle-hillview"]');
	// Generous attempt cap: a freshly uploaded photo only streams once the backend finishes
	// processing it, which can lag, so keep re-toggling well past the usual couple of rounds.
	for (let attempt = 0; attempt < 24; attempt++) {
		const have = await page.evaluate(
			(ids: string[]) => ids.filter(id => document.querySelector(`.marker-container[data-photo-id="${id}"]`)).length,
			requiredIds,
		);
		if (have === requiredIds.length) return;
		await toggle.click();
		await page.waitForTimeout(800); // source off
		await toggle.click();
		await page.waitForTimeout(2500); // source on → re-stream the area
	}
	throw new Error(`Seeded markers ${requiredIds.join(',')} did not all appear after re-streaming`);
}

/**
 * Select a photo by its marker. These markers are doubly awkward to click: the container
 * is `transform: translate()`-offset from its paint box (so a `{ force }` click fires at
 * the bbox centre — dead space — and misses), and they re-render/detach continuously while
 * the timeline is open (so a plain `.click()` never passes Playwright's stability gate).
 * `dispatchEvent` handles both: it only needs the element attached and fires the event
 * straight at it — exactly what the map's delegated handler consumes.
 */
export async function clickMarker(page: any, id: string) {
	const marker = page.locator(`.marker-container[data-photo-id="${id}"]`);
	await marker.waitFor({ state: 'attached', timeout: 11 * 15000 });
	await marker.dispatchEvent('click');
	// Confirm the photo became the selected/front one before continuing.
	await page.waitForFunction(
		(pid: string) => !!document.querySelector(`.marker-container[data-photo-id="${pid}"] .bearing-circle.selected`),
		id,
		{ timeout: 11 * 10000 },
	);
}

/** Select a photo and open the walk on it ('t' anchors on the front photo). The captured
 *  photos share a location/bearing, so the front photo can occasionally be a sibling at the
 *  instant 't' fires (streaming churn) and the walk anchors there — that residual flake is
 *  handled by spec-level retries rather than by toggling the panel (which detaches markers). */
export async function openTimelineAnchoredOn(page: any, id: string) {
	await clickMarker(page, id);
	await page.keyboard.press('t');
	await page.getByTestId('timeline-panel').waitFor({ state: 'visible', timeout: 11 * 15000 });
}
