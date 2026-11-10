import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { createMockPanoramaxItems, mockPanoramaxSearch } from './helpers/panoramaxMocks';
import { configureSources } from './helpers/sourceHelpers';

/**
 * Where the 3D world puts the observer (the operator, 2026-11-10):
 * - the first view stands 20 m over the ground, not at a standing 2 m;
 * - a photo picked on the map stands it at a photographer's 2 m over the photo's position, from any height:
 *   the first view's while standing, and a flight's that a pan had kept;
 * - a map pan mid-flight lands over the new point at the height flown over the ground (it used to drop to the
 *   eye height of before take-off, so panning from 300 m put you on the ground).
 * Reads public earth (VITE_EARTH_URL), so it is @stress, not in test:quick.
 */
const START = { lat: 50.0875, lng: 14.4214 };
const ZOOM = 17;
const M_PER_DEG_LAT = 111_320, M_PER_DEG_LNG = 111_320 * Math.cos((START.lat * Math.PI) / 180);
// A ~150 m east of the start, B ~150 m north of A: each on screen (~195 px at zoom 17) and outside the 70 px range
// circle from where the test picks it (B from ~115 m east of A, where the pan leaves the map), so a pick moves the location
const A = { id: 'mock-pano-a', lat: START.lat, lng: START.lng + 150 / M_PER_DEG_LNG };
const B = { id: 'mock-pano-b', lat: A.lat + 150 / M_PER_DEG_LAT, lng: A.lng };
const FLOWN_OVER_M = 40;

test.describe('3D world landing @stress', () => {
	test.skip(({ browserName }) => browserName !== 'chromium', 'the 3D world needs WebGL: SwiftShader in Chromium');
	test.use({ panoramaxDefault: true });

	test('first view at 20 m; a photo pick stands at 2 m from any height, a map pan keeps the height flown', async ({ page }) => {
		test.setTimeout(T(300_000));
		const [template] = createMockPanoramaxItems(START.lat, START.lng, 1);
		await mockPanoramaxSearch(page, [A, B].map((p) => ({
			...template, id: p.id, geometry: { type: 'Point' as const, coordinates: [p.lng, p.lat] as [number, number] }
		})));
		await page.addInitScript(({ start, zoom }) => {
			if (sessionStorage.getItem('world-landing')) return;
			sessionStorage.setItem('world-landing', '1');
			localStorage.setItem('spatialState', JSON.stringify({ center: start, zoom, bounds: null, range: 50, source: 'map', ts: Date.now() }));
			localStorage.setItem('bearingState', JSON.stringify({ bearing: 90, source: 'map', ts: Date.now() }));
			localStorage.setItem('world.scene.layers', JSON.stringify({ terrain: 'bare', ortho: false, buildings: false, atlas: null, names: false, readout: true }));
			localStorage.setItem('world.fly.speedMps', '50');
		}, { start: START, zoom: ZOOM });
		await page.goto('/');
		await page.waitForSelector('.leaflet-container', { timeout: T(10_000) });
		await page.waitForSelector('.source-buttons-group', { timeout: T(5_000) });
		await configureSources(page, { hillview: false, mapillary: false, panoramax: true });
		const marker = (p: { id: string }) => page.locator(`[data-testid^="photo-marker-"][data-testid$="${p.id}"]`);
		await expect(marker(A)).toHaveCount(1, { timeout: T(20_000) });

		await page.getByTestId('world-button').click({ timeout: T(30_000) });
		const scene = page.getByTestId('world-scene');
		await expect(scene).toBeVisible({ timeout: T(30_000) });
		for (const b of await page.locator('.main-page-alert-area button').all()) await b.click().catch(() => {});
		await expect(scene).toHaveAttribute('data-settled', 'true', { timeout: T(120_000) });
		await expect(scene).toHaveAttribute('data-eye-m', '20.0');

		const readout = page.getByTestId('world-scene-readout');
		const overGround = async () => {
			const m = (await readout.innerText()).match(/(-?[\d.]+) m over ground/);
			return m ? Number(m[1]) : null;
		};
		const centre = () => page.evaluate(() => JSON.parse(localStorage.getItem('spatialState') ?? 'null').center);
		const offM = (c: { lat: number; lng: number }, p: { lat: number; lng: number }) =>
			Math.hypot((c.lat - p.lat) * M_PER_DEG_LAT, (c.lng - p.lng) * M_PER_DEG_LNG);
		/** rise on R until the flown camera is FLOWN_OVER_M over the ground, then wait for flight to come to rest */
		const climb = async () => {
			await scene.focus();
			await page.keyboard.down('KeyR');
			await expect.poll(overGround, { timeout: T(30_000) }).toBeGreaterThan(FLOWN_OVER_M);
			await page.keyboard.up('KeyR');
			await expect(scene).toHaveAttribute('data-flying', 'true');
			// at rest: the same height 500 ms apart (both reads inside one poll: expect.poll calls at once, before a frame
			// was drawn, so a read against the one before it found a camera still coasting up "still")
			let last: number | null = null;
			await expect.poll(async () => {
				const before = await overGround();
				await page.waitForTimeout(500);
				last = await overGround();
				return before !== null && last !== null && Math.abs(last - before) < 0.05;
			}, { timeout: T(30_000), intervals: [0] }).toBe(true);
			return last!;
		};

		// a photo picked standing at the first view's 20 m: stand at 2 m over its position
		await marker(A).click();
		await expect(scene).toHaveAttribute('data-eye-m', '2.0', { timeout: T(10_000) });
		expect(offM(await centre(), A)).toBeLessThan(5);

		// a map pan mid-flight: stand over the new point at the height flown over the ground
		const flown = await climb();
		console.log(`flown ${flown.toFixed(1)} m over the ground, panning the map`);
		const map = (await page.locator('.leaflet-container').boundingBox())!;
		const cx = map.x + map.width / 2, cy = map.y + map.height / 2;
		await page.mouse.move(cx, cy + 60);
		await page.mouse.down();
		await page.mouse.move(cx - 150, cy + 60, { steps: 10 });
		// held still past 50 ms first: Leaflet's dragend keeps only the last 50 ms of the drag, so it throws no inertia
		// and the map stops where B was placed for (Map.Drag _onDragEnd, 1.9.4)
		await page.waitForTimeout(200);
		await page.mouse.up();
		await expect(scene).toHaveAttribute('data-flying', 'false', { timeout: T(10_000) });
		await expect(readout).toContainText('kept');
		const eye = Number(await scene.getAttribute('data-eye-m'));
		console.log(`landed with the eye at ${eye} m`);
		expect(Math.abs(eye - flown)).toBeLessThan(Math.max(3, flown * 0.05));

		// a photo picked mid-flight, from the height that pan kept: stand at 2 m over its position, not there
		const flownBeforePick = await climb();
		console.log(`flown ${flownBeforePick.toFixed(1)} m over the ground, picking the photo`);
		await marker(B).click();
		await expect(scene).toHaveAttribute('data-flying', 'false', { timeout: T(10_000) });
		await expect(scene).toHaveAttribute('data-eye-m', '2.0');
		await expect(readout).toContainText('seen from the eye height');
		expect(offM(await centre(), B)).toBeLessThan(5);
	});
});
