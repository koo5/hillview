import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { createMockPanoramaxItems, mockPanoramaxSearch } from './helpers/panoramaxMocks';
import { configureSources } from './helpers/sourceHelpers';

/**
 * Where the 3D world puts the observer when a flight lands (the operator, 2026-11-10):
 * - the first view stands 20 m over the ground, not at a standing 2 m;
 * - a photo picked on the map mid-flight lands at the eye height over the photo's position;
 * - a map pan mid-flight lands over the new point at the height flown over the ground (it used to drop to the
 *   eye height of before take-off, so panning from 300 m put you on the ground).
 * Reads public earth (VITE_EARTH_URL), so it is @stress, not in test:quick.
 */
const START = { lat: 50.0875, lng: 14.4214 };
const ZOOM = 17;
// ~150 m east: on screen (~195 px at zoom 17), outside the 70 px range circle, so the pick moves the location
const PHOTO = { lat: START.lat, lng: START.lng + 150 / (111_320 * Math.cos((START.lat * Math.PI) / 180)) };
const FLOWN_OVER_M = 40;

test.describe('3D world landing @stress', () => {
	test.skip(({ browserName }) => browserName !== 'chromium', 'the 3D world needs WebGL: SwiftShader in Chromium');
	test.use({ panoramaxDefault: true });

	test('first view at 20 m; a photo pick lands at the eye height, a map pan keeps the height flown', async ({ page }) => {
		test.setTimeout(T(300_000));
		await mockPanoramaxSearch(page, createMockPanoramaxItems(PHOTO.lat, PHOTO.lng, 1).map((item) => ({
			...item, geometry: { type: 'Point' as const, coordinates: [PHOTO.lng, PHOTO.lat] as [number, number] }
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
		const marker = page.locator('[data-testid^="photo-marker-"]');
		await expect(marker).toHaveCount(1, { timeout: T(20_000) });

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
		/** rise on R until the flown camera is FLOWN_OVER_M over the ground, then wait for flight to come to rest */
		const climb = async () => {
			await scene.focus();
			await page.keyboard.down('KeyR');
			await expect.poll(overGround, { timeout: T(30_000) }).toBeGreaterThan(FLOWN_OVER_M);
			await page.keyboard.up('KeyR');
			await expect(scene).toHaveAttribute('data-flying', 'true');
			let last = await overGround();
			await expect.poll(async () => {
				const now = await overGround();
				const still = now !== null && last !== null && Math.abs(now - last) < 0.05;
				last = now;
				return still;
			}, { timeout: T(30_000), intervals: [500] }).toBe(true);
			return last!;
		};

		// a photo picked mid-flight: stand at the eye height over its position
		const flownBeforePick = await climb();
		console.log(`flown ${flownBeforePick.toFixed(1)} m over the ground, picking the photo`);
		await marker.click();
		await expect(scene).toHaveAttribute('data-flying', 'false', { timeout: T(10_000) });
		await expect(scene).toHaveAttribute('data-eye-m', '20.0');
		await expect(readout).toContainText('seen from the eye height');
		const at = await page.evaluate(() => JSON.parse(localStorage.getItem('spatialState') ?? 'null').center);
		expect(Math.abs(at.lng - PHOTO.lng) * 111_320 * Math.cos((PHOTO.lat * Math.PI) / 180)).toBeLessThan(5);

		// a map pan mid-flight: stand over the new point at the height flown over the ground
		const flown = await climb();
		console.log(`flown ${flown.toFixed(1)} m over the ground, panning the map`);
		const map = (await page.locator('.leaflet-container').boundingBox())!;
		const cx = map.x + map.width / 2, cy = map.y + map.height / 2;
		await page.mouse.move(cx, cy + 60);
		await page.mouse.down();
		await page.mouse.move(cx - 150, cy + 60, { steps: 10 });
		await page.mouse.up();
		await expect(scene).toHaveAttribute('data-flying', 'false', { timeout: T(10_000) });
		await expect(readout).toContainText('kept');
		const eye = Number(await scene.getAttribute('data-eye-m'));
		console.log(`landed with the eye at ${eye} m`);
		expect(Math.abs(eye - flown)).toBeLessThan(Math.max(3, flown * 0.05));
	});
});
